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

import os
import re
import stat
import subprocess
from .common import *
from .hashdict import HashDict

GIT = 'git'

canonical_rev_rx = re.compile(r'^[0-9a-f]{40}$')
ls_tree_rx = re.compile(r'^(?P<mode>[0-7]{6}) (?P<type>tree|blob) (?P<object>[0-9a-f]{40})(?: +(?P<size>\d+|-))?\t(?P<name>.+)$', re.I | re.S)
diff_tree_rx = re.compile(r"""
  :
  (?P<src_mode>[0-7]{6})
  [ ]
  (?P<dst_mode>[0-7]{6})
  [ ]
  (?P<src_object>[0-9a-f]{40})
  [ ]
  (?P<dst_object>[0-9a-f]{40})
  [ ]
  (?P<status>.)(?P<score>\d+)?
  \0
  (?P<src_path>[^\0]+)
  \0
  (?:
    (?!:)
    (?P<dst_path>[^\0]+)
    \0
  )?
""", re.VERBOSE)
branch_rx = re.compile(r'^[*]?\s+(?P<name>.+)$')
rev_rx = re.compile(r'^[0-9a-fA-F]{40}$')

class GitRepo(VCSRepo):
  """A git repository

  Valid revisions are anything that git considers as a revision.

  """

  @classmethod
  def create(cls, path):
    """Create a new bare repository"""
    cmd = [GIT, 'init', '--quiet', '--bare', path]
    subprocess.check_call(cmd)
    return cls(path)

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
      cmd = [GIT, 'rev-parse', rev]
      return self._command(cmd)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
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
          cmd = [GIT, 'log', '--pretty=format:%H', '-1', rev]
          entry.commit = self._command(cmd)
        return [entry]
    else:
      cmd = [GIT, 'ls-tree', '-z', rev, '--', path.rstrip('/')]
      output = self._command(cmd)
      output = output.rstrip('\0')
      m = ls_tree_rx.match(output)
      if not m:
        raise PathDoesNotExist(rev, path)
      if m.group('type') == 'tree':
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
    cmd.extend([rev, '--', path])
    output = self._command(cmd).rstrip('\0')
    if not output:
      return []

    results = []
    for line in output.split('\0'):
      m = ls_tree_rx.match(line)
      assert m, 'unexpected output: ' + line
      mode, name, objid = m.group('mode', 'name', 'object')
      if recursive_dirs and path == name + '/':
        continue
      assert name.startswith(path), 'unexpected output: ' + line
      entry = attrdict(path=name)
      entry_name = name[ltrim:].lstrip('/')
      if entry_name:
        entry.name = entry_name
      mode = int(mode, 8)
      if stat.S_ISDIR(mode):
        entry.type = 'd'
      elif stat.S_ISREG(mode):
        entry.type = 'f'
        if 'executable' in report:
          entry.executable = bool(mode & stat.S_IXUSR)
        if 'size' in report:
          entry.size = int(m.group('size'))
      elif stat.S_ISLNK(mode):
        entry.type = 'l'
        if 'target' in report:
          entry.target = self._readlink(rev, name)
      else:
        assert False, 'unexpected output: ' + line
      if 'commit' in report:
        try:
          entry.commit = self._object_cache[objid]
        except KeyError:
          cmd = [GIT, 'log', '--pretty=format:%H', '-1', rev, '--', name]
          commit = str(self._command(cmd))
          entry.commit = self._object_cache[objid] = commit
      results.append(entry)

    return results

  def _cat(self, rev, path):
    cmd = [GIT, 'cat-file', 'blob', '%s:%s' % (rev, path)]
    return self._command(cmd)

  def cat(self, rev, path):
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].get('type') != 'f':
      raise BadFileType(rev, path)
    return self._cat(rev, path)

  def _readlink(self, rev, path):
    cmd = [GIT, 'cat-file', 'blob', '%s:%s' % (rev, path)]
    return self._command(cmd)

  def readlink(self, rev, path):
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].get('type') != 'l':
      raise BadFileType(rev, path)
    return self._readlink(rev, path)

  def branches(self):
    cmd = [GIT, 'branch']
    output = self._command(cmd)
    results = []
    for line in output.splitlines():
      m = branch_rx.match(line)
      assert m, 'unexpected output: ' + line
      results.append(m.group('name'))
    return results

  def tags(self):
    cmd = [GIT, 'tag']
    output = self._command(cmd)
    return output.splitlines()

  def heads(self):
    return self.branches() + self.tags()

  def empty(self):
    cmd = [GIT, 'rev-parse', 'HEAD']
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return not rev_rx.match(stdout.decode())

  def __contains__(self, rev):
    cmd = [GIT, 'rev-list', '-n', '1', rev]
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return p.returncode == 0

  def __len__(self):
    cmd = [GIT, 'rev-list', '--all']
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return len(stdout.splitlines())

  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    cmd = [GIT, 'log', '-z', '--pretty=format:%H%n%P%n%ai%n%an <%ae>%n%B']
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
      entry = self._commit_cache.get(self.canonical_rev(revrange))
      if entry:
        return entry
      cmd.extend(['-1', revrange])
      single = True
    if path:
      if follow:
        cmd.append('--follow')
      cmd.extend(['--', type(self).cleanPath(path)])
    output = self._command(cmd)

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
    cmd = [GIT, 'diff-tree', '-z', '-C', '-r', '-c', '--root', rev]
    output = self._command(cmd)
    results = []
    for m in diff_tree_rx.finditer(output):
      status, src_path, dst_path = m.group('status', 'src_path', 'dst_path')
      if dst_path:
        entry = FileChangeInfo(dst_path, str(status), src_path)
      else:
        entry = FileChangeInfo(src_path, str(status))
      results.append(entry)
    return results

  def pdiff(self, rev):
    cmd = [GIT, 'diff-tree', '-p', '-r', '-c', '--root', rev]
    return self._command(cmd)

  def diff(self, rev_a, rev_b, path=None):
    cmd = [GIT, 'diff', rev_a, rev_b]
    if path is not None:
      cmd.extend(['--', type(self).cleanPath(path)])
    return self._command(cmd)

  def ancestor(self, rev1, rev2):
    cmd = [GIT, 'merge-base', rev1, rev2]
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode == 0:
      return stdout.decode().rstrip()
    elif p.returncode == 1:
      return None
    else:
      raise subprocess.CalledProcessError(p.returncode, cmd, stderr)

  def _blame(self, rev, path):
    cmd = [GIT, 'blame', '--root', '-p', rev, '--', path]
    output = self._command(cmd)
    rev = None
    revinfo = {}
    results = []
    for line in output.splitlines():
      if line.startswith('\t'):
        ri = revinfo[rev]
        author = ri['author'] + ' ' + ri['author-mail']
        ts = int(ri['author-time'])
        tz = UTCOffset(str(ri['author-tz']))
        date = datetime.datetime.fromtimestamp(ts, tz)
        entry = BlameInfo(rev, author, date, line[1:])
        results.append(entry)
      else:
        k, v = line.split(None, 1)
        if rev_rx.match(k):
          rev = k
        else:
          revinfo.setdefault(rev, {})[k] = v
    return results

  def blame(self, rev, path):
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].get('type') != 'f':
      raise BadFileType(rev, path)
    return self._blame(rev, path)
