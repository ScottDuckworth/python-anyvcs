# Copyright (c) 2013-2014, Clemson University
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name Clemson University nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import datetime
import os
import re
import subprocess
import errno
from .common import *

HG = 'hg'

canonical_rev_rx = re.compile(r'^[0-9a-f]{40}$')
manifest_rx = re.compile(r'^(?P<object>[0-9a-f]{40}) (?P<mode>[0-7]{3}) (?P<type>.) (?P<name>.+)$')
parse_heads_rx = re.compile(r'^(?P<name>.+?)\s+(?P<rev>-?\d+):(?P<nodeid>[0-9a-f]+)', re.I)
bookmarks_rx = re.compile(r'^\s+(?:\*\s+)?(?P<name>.+?)\s+(?P<rev>[-]?\d+):(?P<nodeid>[0-9a-f]+)', re.I)
annotate_rx = re.compile(r'^(?P<author>.*)\s+(?P<rev>\d+):\s')


def parent_dirs(path):
    ds = path.find('/')
    while ds != -1:
        yield path[:ds]
        ds = path.find('/', ds + 1)


def parse_hgdate(datestr):
    ts, tzoffset = datestr.split(None, 1)
    date = datetime.datetime.fromtimestamp(float(ts))
    return date.replace(tzinfo=UTCOffset(-int(tzoffset) / 60))


class HgRepo(VCSRepo):
    """A Mercurial repository

    Valid revisions are anything that Mercurial considers as a revision.

    """

    @classmethod
    def clone(cls, srcpath, destpath):
        """Clone an existing repository to a new bare repository."""
        # Mercurial will not create intermediate directories for clones.
        try:
            os.makedirs(destpath)
        except OSError as e:
            if not e.errno == errno.EEXIST:
                raise
        cmd = [HG, 'clone', '--quiet', '--noupdate', srcpath, destpath]
        subprocess.check_call(cmd)
        return cls(destpath)

    @classmethod
    def create(cls, path):
        """Create a new repository"""
        cmd = [HG, 'init', path]
        subprocess.check_call(cmd)
        return cls(path)

    @property
    def private_path(self):
        """Get the path to a directory which can be used to store arbitrary data

        This directory should not conflict with any of the repository internals.
        The directory should be created if it does not already exist.

        """
        path = os.path.join(self.path, '.hg', '.private')
        try:
            os.mkdir(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        return path

    @property
    def _object_cache(self):
        try:
            return self._object_cache_v
        except AttributeError:
            object_cache_path = os.path.join(self.private_path, 'object-cache')
            self._object_cache_v = HashDict(object_cache_path)
            return self._object_cache_v

    def canonical_rev(self, rev):
        if isinstance(rev, str) and canonical_rev_rx.match(rev):
            return rev
        else:
            cmd = [HG, 'log', '--template={node}', '-r', str(rev)]
            return self._command(cmd).decode()

    def compose_rev(self, branch, rev):
        return self.canonical_rev(rev)

    def _revnum(self, rev):
        if isinstance(rev, int):
            return rev
        elif isinstance(rev, str) and rev.isdigit():
            return int(rev)
        else:
            cmd = [HG, 'log', '--template={rev}', '-r', str(rev)]
            return int(self._command(cmd))

    def _ls(
        self, rev, path, recursive=False, recursive_dirs=False, directory=False
    ):
        forcedir = False
        if path.endswith('/'):
            forcedir = True
            path = path.rstrip('/')
        if path == '':
            ltrim = 0
            prefix = ''
        else:
            ltrim = len(path) + 1
            prefix = path + '/'
        cmd = [HG, 'manifest', '--debug', '-r', rev]
        output = self._command(cmd).decode(self.encoding, 'replace')
        if not output:
            return

        dirs = set()
        exists = False
        for line in output.splitlines():
            m = manifest_rx.match(line)
            assert m, 'unexpected output: ' + line
            t, name, objid = m.group('type', 'name', 'object')
            if name.startswith(prefix) or (not forcedir and name == path):
                if directory and name.startswith(prefix):
                    yield ('d', path, '', None)
                    return
                exists = True
                entry_name = name[ltrim:]
                if '/' in entry_name:
                    p = parent_dirs(entry_name)
                    if not recursive:
                        d = next(p)
                        if d not in dirs:
                            dirs.add(d)
                            yield ('d', prefix + d, d, None)
                        continue
                    if recursive_dirs:
                        for d in p:
                            if d not in dirs:
                                dirs.add(d)
                                yield ('d', prefix + d, d, None)
                yield (t, name, entry_name, objid)
        if not exists:
            raise PathDoesNotExist(rev, path)

    def ls(
        self, rev, path, recursive=False, recursive_dirs=False,
        directory=False, report=()
    ):
        revstr = str(rev)
        path = type(self).cleanPath(path)
        if path == '':
            if directory:
                entry = attrdict(path='/', type='d')
                if 'commit' in report:
                    entry.commit = self.canonical_rev(revstr)
                return [entry]

        if 'commit' in report:
            import fcntl
            import tempfile
            files_cache_path = os.path.join(self.private_path, 'files-cache.log')
            with open(files_cache_path, 'a+') as files_cache:
                fcntl.lockf(files_cache, fcntl.LOCK_EX, 0, 0, os.SEEK_CUR)
                files_cache.seek(0)
                log = files_cache.read().split('\0')
                assert log.pop() == ''
                if log:
                    startlog = int(log[-1].splitlines()[0]) + 1
                    if startlog >= len(self):
                        startlog = None
                else:
                    startlog = 0
                if startlog is not None:
                    with tempfile.NamedTemporaryFile() as style:
                        style.write((
                            r"changeset = '{rev}\n{node}\n{parents}\n{files}\0'" '\n'
                            r"parent = '{rev} '" '\n'
                            r"file = '{file|escape}\n'" '\n'
                        ).encode())
                        style.flush()
                        cmd = [HG, 'log', '--style', style.name, '-r', '%d:' % startlog]
                        output = self._command(cmd).decode(self.encoding, 'replace')
                        files_cache.write(output)
                        extend = output.split('\0')
                        assert extend.pop() == ''
                        log.extend(extend)

        results = []
        lookup_commit = {}
        for t, fullpath, name, objid in self._ls(revstr, path, recursive, recursive_dirs, directory):
            entry = attrdict(path=fullpath)
            if name:
                entry.name = name
            if t == 'd':
                entry.type = 'd'
            elif t in ' *':
                entry.type = 'f'
                if 'executable' in report:
                    entry.executable = t == '*'
                if 'size' in report:
                    entry.size = len(self._cat(revstr, fullpath))
            elif t == '@':
                entry.type = 'l'
                if 'target' in report:
                    entry.target = self._cat(revstr, name).decode(self.encoding, 'replace')
            else:
                assert False, 'unexpected output: ' + line
            if 'commit' in report:
                lookup = True
                if objid:
                    try:
                        import hashlib
                        concat = (fullpath + objid).encode(self.encoding)
                        k = hashlib.sha1(concat).hexdigest()
                        entry.commit = self._object_cache[k].decode()
                        entry._commit_cached = True
                        lookup = False
                    except KeyError:
                        pass
                if lookup:
                    if name:
                        p = type(self).cleanPath(path + '/' + name)
                    else:
                        p = path
                    lookup_commit[p] = (entry, objid)
            results.append(entry)

        if 'commit' in report:
            import heapq
            ancestors = [-self._revnum(revstr)]
            while ancestors and lookup_commit:
                r = -heapq.heappop(ancestors)
                lines = log[r].splitlines()
                parents = lines[2]
                if parents:
                    for x in parents.split():
                        x = int(x)
                        if x != -1:
                            if -x not in ancestors:
                                heapq.heappush(ancestors, -x)
                elif r > 0:
                    x = r - 1
                    if x not in ancestors:
                        heapq.heappush(ancestors, -x)
                for p in list(lookup_commit):
                    prefix = p.rstrip('/') + '/'
                    for l in lines[3:]:
                        if l == p or l.startswith(prefix):
                            commit = str(lines[1])
                            entry, objid = lookup_commit[p]
                            entry.commit = commit
                            if objid:
                                import hashlib
                                concat = (p + objid).encode(self.encoding)
                                k = hashlib.sha1(concat).hexdigest()
                                self._object_cache[k] = commit.encode()
                            del lookup_commit[p]
                            break

        return results

    def _cat(self, rev, path):
        cmd = [HG, 'cat', '-r', rev, path.encode(self.encoding)]
        return self._command(cmd)

    def cat(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'f':
            raise BadFileType(rev, path)
        return self._cat(str(rev), path)

    def readlink(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'l':
            raise BadFileType(rev, path)
        return self._cat(str(rev), path).decode(self.encoding, 'replace')

    def _parse_heads(self, cmd):
        output = self._command(cmd).decode(self.encoding, 'replace')
        results = []
        for line in output.splitlines():
            m = parse_heads_rx.match(line)
            assert m, 'unexpected output: ' + line
            results.append(m.group('name'))
        return results

    def branches(self):
        cmd = [HG, 'branches']
        return self._parse_heads(cmd)

    def tags(self):
        cmd = [HG, 'tags']
        return self._parse_heads(cmd)

    def bookmarks(self):
        """Get list of bookmarks"""
        cmd = [HG, 'bookmarks']
        output = self._command(cmd).decode(self.encoding, 'replace')
        if output.startswith('no bookmarks set'):
            return []
        results = []
        for line in output.splitlines():
            m = bookmarks_rx.match(line)
            assert m, 'unexpected output: ' + line
            results.append(m.group('name'))
        return results

    def heads(self):
        return self.branches() + self.tags() + self.bookmarks()

    def empty(self):
        cmd = [HG, 'log', '--template=a', '-l1']
        output = self._command(cmd)
        return len(output) == 0

    def __contains__(self, rev):
        cmd = [HG, 'log', '--template=a', '-r', str(rev)]
        p = subprocess.Popen(
            cmd, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        return p.returncode == 0

    def __len__(self):
        cmd = [HG, 'id', '-n', '-r', 'tip']
        output = self._command(cmd)
        return int(output) + 1

    def log(
        self, revrange=None, limit=None, firstparent=False, merges=None,
        path=None, follow=False
    ):
        cmd = [
            HG, 'log', '--debug', '--template={node}\\0{parents}\\0'
            '{date|hgdate}\\0{author|nonempty}'
            '\\0{desc|tabindent|nonempty}\\0\\0']
        if limit is not None:
            cmd.append('-l' + str(limit))
        if firstparent:
            cmd.append('--follow-first')
        if merges is not None:
            if merges:
                cmd.append('--only-merges')
            else:
                cmd.append('--no-merges')
        single = False
        if revrange is None:
            pass
        elif isinstance(revrange, (tuple, list)):
            if revrange[0] is None:
                if revrange[1] is None:
                    pass
                else:
                    cmd.extend(['-r', 'reverse(ancestors(%s))' % revrange[1]])
            else:
                if revrange[1] is None:
                    cmd.extend(['-r', 'reverse(descendants(%s))' % revrange[0]])
                else:
                    cmd.extend(['-r', 'reverse(ancestors(%s))' % revrange[1], '--prune', str(revrange[0])])
        else:
            entry = self._commit_cache.get(self.canonical_rev(revrange))
            if entry:
                entry._cached = True
                return entry
            cmd.extend(['-r', str(revrange)])
            single = True
        if path:
            if follow:
                cmd.append('--follow')
            cmd.extend(['--', type(self).cleanPath(path)])
        output = self._command(cmd).decode(self.encoding, 'replace')

        results = []
        logs = output.split('\0\0')
        logs.pop()
        for log in logs:
            rev, parents, date, author, message = log.split('\0', 4)
            parents = [
                x[1] for x in filter(
                    lambda x: x[0] != '-1',
                    (x.split(':') for x in parents.split())
                )
            ]
            date = parse_hgdate(date)
            message = message.replace('\n\t', '\n')
            entry = CommitLogEntry(rev, parents, date, author, message)
            if rev not in self._commit_cache:
                self._commit_cache[rev] = entry
            if single:
                return entry
            results.append(entry)
        return results

    def changed(self, rev):
        cmd = [HG, 'status', '-C', '--change', str(rev)]
        output = self._command(cmd).decode(self.encoding, 'replace')
        results = []
        copy = None
        for line in reversed(output.splitlines()):
            if line.startswith(' '):
                copy = line.lstrip()
            else:
                status, path = line.split(None, 1)
                entry = FileChangeInfo(path, str(status), copy)
                results.append(entry)
                copy = None
        results.reverse()
        return results

    def pdiff(self, rev):
        cmd = [HG, 'log', '--template=a', '-p', '-r', str(rev)]
        return self._command(cmd)[1:].decode(self.encoding)

    def diff(self, rev_a, rev_b, path=None):
        cmd = [HG, 'diff', '-r', rev_a, '-r', rev_b]
        if path is not None:
            cmd.extend(['--', type(self).cleanPath(path)])
        return self._command(cmd).decode(self.encoding)

    def ancestor(self, rev1, rev2):
        cmd = [HG, 'log', '--template={node}', '-r', 'ancestor(%s, %s)' % (rev1, rev2)]
        output = self._command(cmd).decode()
        if output == '':
            return None
        else:
            return output

    def _blame(self, rev, path):
        cmd = [HG, 'annotate', '-unv', '-r', rev, '--', path]
        output = self._command(cmd).decode(self.encoding, 'replace')
        revs = {}
        results = []
        cat = self._cat(rev, path)
        for line, text in zip(output.splitlines(), cat.splitlines()):
            m = annotate_rx.match(line)
            assert m, 'unexpected output: ' + line
            rev, author = m.group('rev', 'author')
            try:
                rev, date = revs[rev]
            except KeyError:
                cmd = [HG, 'log', '--template={node}\n{date|hgdate}', '-r', rev]
                output = self._command(cmd).decode(self.encoding, 'replace')
                rev, date = output.split('\n', 1)
                date = parse_hgdate(date)
                revs[rev] = rev, date
            results.append(BlameInfo(rev, author, date, text))
        return results

    def blame(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'f':
            raise BadFileType(rev, path)
        return self._blame(str(rev), path)

    def tip(self, head):
        return self.canonical_rev(head)

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
