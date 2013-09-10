import re
import stat
import subprocess
from common import *

GIT = 'git'

ls_tree_rx = re.compile(r'^(?P<mode>[0-7]{6}) (?P<type>tree|blob) (?:[0-9a-f]{40})(?: +(?P<size>\d+|-))?\t(?P<name>.+)$', re.I | re.S)
branch_rx = re.compile(r'^[*]?\s+(?P<name>.+)$')

class GitRepo(VCSRepo):
  @classmethod
  def create(cls, path):
    cmd = [GIT, 'init', '--quiet', '--bare', path]
    subprocess.check_call(cmd)
    return cls(path)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    forcedir = False
    if directory and path.endswith('/'):
      forcedir = True
      path = path.rstrip('/')
    ltrim = len(path)

    # make sure the path exists
    if path == '':
      if directory:
        return [{'type':'d'}]
    else:
      cmd = [GIT, 'ls-tree', '-z', rev, '--', path]
      output = self._command(cmd).rstrip('\0')
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

    results = []
    for line in output.split('\0'):
      m = ls_tree_rx.match(line)
      assert m, 'unexpected output: ' + line
      mode, name = m.group('mode', 'name')
      if recursive_dirs and path == name + '/':
        continue
      assert name.startswith(path), 'unexpected output: ' + line
      entry = attrdict()
      entry_name = name[ltrim:].lstrip('/')
      if entry_name:
        entry.name = entry_name
      mode = int(mode, 8)
      if stat.S_ISDIR(mode):
        entry.type = 'd'
      elif forcedir:
        continue
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
      results.append(entry)
    return results

  def cat(self, rev, path):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'f':
      raise BadFileType(rev, path)
    cmd = [GIT, 'cat-file', 'blob', '%s:%s' % (rev, path)]
    return self._command(cmd)

  def _readlink(self, rev, path):
    cmd = [GIT, 'cat-file', 'blob', '%s:%s' % (rev, path)]
    return self._command(cmd)

  def readlink(self, rev, path):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'l':
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
