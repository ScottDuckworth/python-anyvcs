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

  def log(self, revrange=None, limit=None, branchlog=False, firstparent=False,
          merges=None, path=None, follow=False):
    cmd = [GIT, 'log', '--pretty=format:%H%n:%P%n%ai%n%an <%ae>%n:%s%n%n']
    if limit is not None:
      cmd.append('-' + str(limit))
    if firstparent:
      cmd.append('--first-parent')
    if merges is not None:
      if merges:
        cmd.append('--merges')
      else:
        cmd.append('--no-merges')
    if revrange is None:
      pass
    elif isinstance(revrange, tuple):
      if revrange[0] is None:
        if revrange[1] is None:
          pass
        else:
          cmd.append(revrange[1])
      else:
        if revrange[1] is None:
          cmd.append(revrange[0] + '..')
        else:
          cmd.append(revrange[0] + '..' + revrange[1])
    else:
      cmd.extend(['-1', revrange])
    if path:
      if follow:
        cmd.append('--follow')
      cmd.extend(['--', type(self).cleanPath(path)])
    output = self._command(cmd)

    results = []
    for log in output.split('\n\n')[:-1]:
      rev, parents, date, author, subject = log.split('\n', 4)
      parents = parents[1:].split()
      date = parse_isodate(date)
      subject = subject[1:]
      results.append(CommitLogEntry(rev, parents, date, author, subject))
    return results

  def diff(self, rev_a, rev_b, path_a, path_b=None):
    raise NotImplementedError
