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

import os
import re
import stat
import subprocess
from .common import *
from .hashdict import HashDict

GIT = 'git'

rev_rx = re.compile(r'^[0-9a-f]{40}$', re.IGNORECASE)
branch_rx = re.compile(r'^[*]?\s+(?P<name>.+)$')


def readuntil(f, stop):
    buf = bytes()
    while True:
        b = f.read(1)
        if b == stop or not b:
            return buf
        buf += b


class GitRepo(VCSRepo):
    """A git repository

    Valid revisions are anything that git considers as a revision.

    """

    @classmethod
    def clone(cls, srcpath, destpath, encoding='utf-8'):
        """Clone an existing repository to a new bare repository."""
        cmd = [GIT, 'clone', '--quiet', '--bare', srcpath, destpath]
        subprocess.check_call(cmd)
        return cls(destpath, encoding)

    @classmethod
    def create(cls, path, encoding='utf-8'):
        """Create a new bare repository"""
        cmd = [GIT, 'init', '--quiet', '--bare', path]
        subprocess.check_call(cmd)
        return cls(path, encoding)

    @property
    def private_path(self):
        """Get the path to a directory which can be used to store arbitrary data

        This directory should not conflict with any of the repository internals.
        The directory should be created if it does not already exist.

        """
        path = os.path.join(self.path, '.private')
        try:
            os.mkdir(path)
        except OSError as e:
            import errno
            if e.errno != errno.EEXIST:
                raise
        return path

    def canonical_rev(self, rev):
        rev = str(rev)
        if rev_rx.match(rev):
            return rev
        else:
            cmd = [GIT, 'rev-parse', rev]
            return self._command(cmd).decode().rstrip()

    def compose_rev(self, branch, rev):
        return self.canonical_rev(rev)

    def ls(
        self, rev, path, recursive=False, recursive_dirs=False,
        directory=False, report=()
    ):
        rev = self.canonical_rev(rev)
        path = type(self).cleanPath(path)
        forcedir = False
        if path.endswith('/'):
            forcedir = True
            path = path.rstrip('/')
        ltrim = len(path)

        # make sure the path exists
        if path == '':
            if directory:
                entry = attrdict(path='/', type='d')
                if 'commit' in report:
                    entry.commit = rev
                return [entry]
        else:
            epath = path.rstrip('/').encode(self.encoding)
            cmd = [GIT, 'ls-tree', '-z', rev, '--', epath]
            output = self._command(cmd)
            if not output:
                raise PathDoesNotExist(rev, path)
            meta, ename = output.split(b'\t', 1)
            meta = meta.decode().split()
            if meta[1] == 'tree':
                if not (directory or path.endswith('/')):
                    path = path + '/'
            elif forcedir:
                raise PathDoesNotExist(rev, path)

        cmd = [GIT, 'ls-tree', '-z']
        if recursive:
            cmd.append('-r')
            if recursive_dirs:
                cmd.append('-t')
        if 'size' in report:
            cmd.append('-l')
        epath = path.encode(self.encoding)
        cmd.extend([rev, '--', epath])
        output = self._command(cmd).rstrip(b'\0')
        if not output:
            return []

        results = []
        files = {}
        for line in output.split(b'\0'):
            meta, ename = line.split(b'\t', 1)
            meta = meta.decode().split()
            mode = int(meta[0], 8)
            name = ename.decode(self.encoding, 'replace')
            if recursive_dirs and path == name + '/':
                continue
            assert name.startswith(path), 'unexpected output: ' + str(line)
            entry = attrdict(path=name)
            entry_name = name[ltrim:].lstrip('/')
            if entry_name:
                entry.name = entry_name
            if stat.S_ISDIR(mode):
                entry.type = 'd'
            elif stat.S_ISREG(mode):
                entry.type = 'f'
                if 'executable' in report:
                    entry.executable = bool(mode & stat.S_IXUSR)
                if 'size' in report:
                    entry.size = int(meta[3])
            elif stat.S_ISLNK(mode):
                entry.type = 'l'
                if 'target' in report:
                    entry.target = self._cat(rev, ename).decode(self.encoding, 'replace')
            else:
                assert False, 'unexpected output: ' + str(line)
            results.append(entry)
            files[ename] = entry

        if 'commit' in report:
            cmd = [GIT, 'log', '--pretty=format:%H', '--name-only', '-m', '--first-parent', '-z', rev]
            p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE)
            commit = readuntil(p.stdout, b'\n').rstrip().split(b'\0')[-1]
            while commit and files:
                while True:
                    f = readuntil(p.stdout, b'\0')
                    if f == b'':
                        commit = readuntil(p.stdout, b'\n').split(b'\0')[-1]
                        break
                    if not recursive:
                        d = f[len(path):].find(b'/')
                        if d != -1:
                            f = f[:len(path) + d]
                    if f in files:
                        files[f].commit = commit.decode()
                        del files[f]
            p.stdout.close()
            p.terminate()
            p.wait()

        return results

    def _cat(self, rev, path):
        rp = rev.encode('ascii') + b':' + path
        cmd = [GIT, 'cat-file', 'blob', rp]
        return self._command(cmd)

    def cat(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'f':
            raise BadFileType(rev, path)
        epath = path.encode(self.encoding, 'strict')
        return self._cat(rev, epath)

    def readlink(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'l':
            raise BadFileType(rev, path)
        epath = path.encode(self.encoding, 'strict')
        return self._cat(rev, epath).decode(self.encoding, 'replace')

    def branches(self):
        cmd = [GIT, 'branch']
        output = self._command(cmd).decode(self.encoding, 'replace')
        results = []
        for line in output.splitlines():
            m = branch_rx.match(line)
            assert m, 'unexpected output: ' + str(line)
            results.append(m.group('name'))
        return results

    def tags(self):
        cmd = [GIT, 'tag']
        output = self._command(cmd).decode(self.encoding, 'replace')
        return output.splitlines()

    def heads(self):
        return self.branches() + self.tags()

    def empty(self):
        cmd = [GIT, 'rev-list', '-n1', '--all']
        p = subprocess.Popen(
            cmd, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        return not rev_rx.match(stdout.decode())

    def __contains__(self, rev):
        cmd = [GIT, 'rev-list', '-n', '1', rev]
        p = subprocess.Popen(
            cmd, cwd=self.path, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        return p.returncode == 0

    def __len__(self):
        cmd = [GIT, 'rev-list', '--all']
        p = subprocess.Popen(
            cmd, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        return len(stdout.splitlines())

    def log(
        self, revrange=None, limit=None, firstparent=False, merges=None,
        path=None, follow=False
    ):
        cmd = [GIT, 'log', '-z', '--pretty=format:%H%n%P%n%ai%n%an <%ae>%n%B', '--encoding=none']
        if limit is not None:
            cmd.append('-' + str(limit))
        if firstparent:
            cmd.append('--first-parent')
        if merges is not None:
            if merges:
                cmd.append('--merges')
            else:
                cmd.append('--no-merges')
        single = False
        if revrange is None:
            if self.empty():
                return []
            cmd.append('--all')
        elif isinstance(revrange, (tuple, list)):
            if revrange[0] is None:
                if revrange[1] is None:
                    if self.empty():
                        return []
                    cmd.append('--all')
                else:
                    cmd.append(revrange[1])
            else:
                if revrange[1] is None:
                    cmd.append(revrange[0] + '..')
                else:
                    cmd.append(revrange[0] + '..' + revrange[1])
        else:
            rev = self.canonical_rev(revrange)
            entry = self._commit_cache.get(rev)
            if entry:
                entry._cached = True
                return entry
            cmd.extend(['-1', rev])
            single = True
        if path:
            if follow:
                cmd.append('--follow')
            cmd.extend(['--', type(self).cleanPath(path)])
        output = self._command(cmd).decode(self.encoding, 'replace')

        results = []
        for log in output.split('\0'):
            rev, parents, date, author, message = log.split('\n', 4)
            parents = parents.split()
            date = parse_isodate(date)
            entry = CommitLogEntry(rev, parents, date, author, message)
            if rev not in self._commit_cache:
                self._commit_cache[rev] = entry
            if single:
                return entry
            results.append(entry)
        return results

    def changed(self, rev):
        cmd = [GIT, 'diff-tree', '-z', '-C', '-r', '-m', '--no-commit-id', '--first-parent', '--root', rev]
        output = self._command(cmd)
        results = []
        for line in output.rstrip(b'\0').split(b'\0:'):
            path = line.split(b'\0')
            meta = path.pop(0).split()
            status = meta[3].decode()[0]
            src_path = path[0].decode(self.encoding, 'replace')
            if len(path) == 2:
                dst_path = path[1].decode(self.encoding, 'replace')
                entry = FileChangeInfo(dst_path, str(status), src_path)
            else:
                entry = FileChangeInfo(src_path, str(status))
            results.append(entry)
        return results

    def pdiff(self, rev):
        cmd = [GIT, 'diff-tree', '-p', '-r', '-m', '--no-commit-id', '--first-parent', '--root', rev]
        return self._command(cmd).decode(self.encoding)

    def diff(self, rev_a, rev_b, path=None):
        cmd = [GIT, 'diff', rev_a, rev_b]
        if path is not None:
            cmd.extend(['--', type(self).cleanPath(path)])
        return self._command(cmd).decode(self.encoding)

    def ancestor(self, rev1, rev2):
        cmd = [GIT, 'merge-base', rev1, rev2]
        p = subprocess.Popen(
            cmd, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = p.communicate()
        if p.returncode == 0:
            return stdout.decode().rstrip()
        elif p.returncode == 1:
            return None
        else:
            raise subprocess.CalledProcessError(p.returncode, cmd, stderr)

    def blame(self, rev, path):
        path = type(self).cleanPath(path)
        ls = self.ls(rev, path, directory=True)
        assert len(ls) == 1
        if ls[0].get('type') != 'f':
            raise BadFileType(rev, path)
        cmd = [GIT, 'blame', '--root', '--encoding=none', '-p', rev, '--', path]
        output = self._command(cmd)
        rev = None
        revinfo = {}
        results = []
        for line in output.splitlines():
            if line.startswith(b'\t'):
                ri = revinfo[rev]
                author = ri['author'] + ' ' + ri['author-mail']
                ts = int(ri['author-time'])
                tz = UTCOffset(str(ri['author-tz']))
                date = datetime.datetime.fromtimestamp(ts, tz)
                entry = BlameInfo(rev, author, date, line[1:])
                results.append(entry)
            else:
                k, v = line.decode(self.encoding, 'replace').split(None, 1)
                if rev_rx.match(k):
                    rev = k
                else:
                    revinfo.setdefault(rev, {})[k] = v
        return results

    def tip(self, head):
        return self.canonical_rev(head)

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
