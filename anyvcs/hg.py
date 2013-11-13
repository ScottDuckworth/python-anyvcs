# Copyright 2013 Clemson University
#
# This file is part of python-anyvcs.
#
# python-anyvcs is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# python-anyvcs is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with python-anyvcs.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import os
import re
import subprocess
from .common import *

HG = 'hg'

canonical_rev_rx = re.compile(r'^[0-9a-f]{40}$')
manifest_rx = re.compile(r'^(?P<object>[0-9a-f]{40}) (?P<mode>[0-7]{3}) (?P<type>.) (?P<name>.+)$')
parse_heads_rx = re.compile(r'^(?P<name>.+?)\s+(?P<rev>-?\d+):(?P<nodeid>[0-9a-f]+)', re.I)
bookmarks_rx = re.compile(r'^\s+(?:\*\s+)?(?P<name>.+?)\s+(?P<rev>\d+):(?P<nodeid>[0-9a-f]+)', re.I)
annotate_rx = re.compile(r'^(?P<author>.*)\s+(?P<rev>\d+):\s')

def parent_dirs(path):
  ds = path.find('/')
  while ds != -1:
    yield path[:ds]
    ds = path.find('/', ds + 1)

def parse_hgdate(datestr):
  ts, tzoffset = datestr.split(None, 1)
  date = datetime.datetime.fromtimestamp(float(ts))
  return date.replace(tzinfo=UTCOffset(-int(tzoffset)/60))

class HgRepo(VCSRepo):
  """A Mercurial repository

  Valid revisions are anything that Mercurial considers as a revision.

  """

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
      import errno
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
      return self._command(cmd)

  def _revnum(self, rev):
    if isinstance(rev, int):
      return rev
    elif isinstance(rev, (str, unicode)) and rev.isdigit():
      return int(rev)
    else:
      cmd = [HG, 'log', '--template={rev}', '-r', str(rev)]
      return int(self._command(cmd))

  def _ls(self, rev, path, recursive=False, recursive_dirs=False,
          directory=False):
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
    output = self._command(cmd)
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
            d = p.next()
            if d not in dirs:
              dirs.add(d)
              yield ('d', prefix+d, d, None)
            continue
          if recursive_dirs:
            for d in p:
              if d not in dirs:
                dirs.add(d)
                yield ('d', prefix+d, d, None)
        yield (t, name, entry_name, objid)
    if not exists:
      raise PathDoesNotExist(rev, path)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    revstr = str(rev)
    path = type(self).cleanPath(path)
    if path == '':
      if directory:
        entry = attrdict(path='/', type='d')
        if 'commit' in report:
          entry.commit = self.canonical_rev(revstr)
        return [entry]

    if 'commit' in report:
      import fcntl, tempfile
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
            style.write(
              r"changeset = '{rev}\n{node}\n{parents}\n{files}\0'" '\n'
              r"parent = '{rev} '" '\n'
              r"file = '{file|escape}\n'" '\n'
            )
            style.flush()
            cmd = [HG, 'log', '--style', style.name, '-r', '%d:' % startlog]
            output = self._command(cmd)
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
          entry.size = len(self._cat(revstr, name))
      elif t == '@':
        entry.type = 'l'
        if 'target' in report:
          entry.target = self._cat(revstr, name)
      else:
        assert False, 'unexpected output: ' + line
      if 'commit' in report:
        lookup = True
        if objid:
          try:
            entry.commit = self._object_cache[objid]
            lookup = False
          except KeyError:
            pass
        if lookup:
          p = type(self).cleanPath(path + '/' + name)
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
        for p in lookup_commit.keys():
          prefix = p.rstrip('/') + '/'
          for l in lines[3:]:
            if l == p or l.startswith(prefix):
              commit = lines[1]
              entry, objid = lookup_commit[p]
              entry.commit = commit
              if objid:
                self._object_cache[objid] = commit
              del lookup_commit[p]
              break

    return results

  def _cat(self, rev, path):
    cmd = [HG, 'cat', '-r', rev, path]
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
    return self._cat(str(rev), path)

  def _parse_heads(self, cmd):
    output = self._command(cmd)
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
    output = self._command(cmd)
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
    return output == ''

  def __contains__(self, rev):
    cmd = [HG, 'log', '--template=a', '-r', str(rev)]
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return p.returncode == 0

  def __len__(self):
    cmd = [HG, 'id', '-n', '-r', 'tip']
    output = self._command(cmd)
    return int(output) + 1

  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    cmd = [HG, 'log', '--debug', '--template={node}\\0{parents}\\0'
           '{date|hgdate}\\0{author|nonempty}\\0{desc|tabindent|nonempty}\\0\\0']
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
        return entry
      cmd.extend(['-r', str(revrange)])
      single = True
    if path:
      if follow:
        cmd.append('--follow')
      cmd.extend(['--', type(self).cleanPath(path)])
    output = self._command(cmd)

    results = []
    logs = output.split('\0\0')
    logs.pop()
    for log in logs:
      rev, parents, date, author, message = log.split('\0', 4)
      parents = [x[1] for x in filter(lambda x: x[0] != '-1',
        (x.split(':') for x in parents.split()))]
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
    output = self._command(cmd)
    results = []
    copy = None
    for line in reversed(output.splitlines()):
      if line.startswith(' '):
        copy = line.lstrip()
      else:
        status, path = line.split(None, 1)
        entry = FileChangeInfo(path, status, copy)
        results.append(entry)
        copy = None
    results.reverse()
    return results

  def pdiff(self, rev):
    cmd = [HG, 'log', '--template=a', '-p', '-r', str(rev)]
    return self._command(cmd)[1:]

  def pdiff(self, rev):
    cmd = [HG, 'log', '--template=a', '-p', '-r', str(rev)]
    return self._command(cmd)[1:]

  def diff(self, rev_a, rev_b, path=None):
    cmd = [HG, 'diff', '-r', rev_a, '-r', rev_b]
    if path is not None:
      cmd.extend(['--', type(self).cleanPath(path)])
    return self._command(cmd)

  def ancestor(self, rev1, rev2):
    cmd = [HG, 'log', '--template={node}', '-r', 'ancestor(%s, %s)' % (rev1, rev2)]
    output = self._command(cmd)
    if output == '':
      return None
    else:
      return output

  def _blame(self, rev, path):
    cmd = [HG, 'annotate', '-unv', '-r', rev, '--', path]
    output = self._command(cmd)
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
        rev, date = self._command(cmd).split('\n', 1)
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
