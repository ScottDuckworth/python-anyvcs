import datetime
import re
import subprocess
from common import *

HG = 'hg'

manifest_rx = re.compile(r'^(?P<mode>[0-7]{3}) (?P<type>.) (?P<name>.+)$')
parse_heads_rx = re.compile(r'^(?P<name>.+?)\s+(?P<rev>\d+):(?P<nodeid>[0-9a-f]+)', re.I)
bookmarks_rx = re.compile(r'^\s+(?:\*\s+)?(?P<name>.+?)\s+(?P<rev>\d+):(?P<nodeid>[0-9a-f]+)', re.I)

def parent_dirs(path):
  ds = path.find('/')
  while ds != -1:
    yield path[:ds]
    ds = path.find('/', ds + 1)

class HgRepo(VCSRepo):
  @classmethod
  def create(cls, path):
    cmd = [HG, 'init', path]
    subprocess.check_call(cmd)
    return cls(path)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    forcedir = False
    if path.endswith('/'):
      forcedir = True
      path = path.rstrip('/')
    if path == '':
      if directory:
        return [{'type':'d'}]
      ltrim = 0
      prefix = ''
    else:
      ltrim = len(path) + 1
      prefix = path + '/'

    cmd = [HG, 'manifest', '-v', '-r', rev]
    output = self._command(cmd)
    dirs = set()
    results = []
    for line in output.splitlines():
      m = manifest_rx.match(line)
      assert m, 'unexpected output: ' + line
      t, name = m.group('type', 'name')
      if name.startswith(prefix) or (not forcedir and name == path):
        entry_name = name[ltrim:]
        if '/' in entry_name:
          p = parent_dirs(entry_name)
          if not recursive:
            d = p.next()
            if d not in dirs:
              dirs.add(d)
              entry = attrdict(type='d')
              if not directory:
                entry.name = d
              results.append(entry)
            continue
          if recursive_dirs:
            for d in p:
              if d not in dirs:
                dirs.add(d)
                entry = attrdict(name=d, type='d')
                results.append(entry)
        entry = attrdict()
        if entry_name:
          entry.name = entry_name
        if t in ' *':
          entry.type = 'f'
          if 'executable' in report:
            entry.executable = t == '*'
          if 'size' in report:
            entry.size = len(self.cat(rev, name))
        elif t == '@':
          entry.type = 'l'
          if 'target' in report:
            entry.target = self._readlink(rev, name)
        else:
          assert False, 'unexpected output: ' + line
        results.append(entry)
    if not results and path != '':
      raise PathDoesNotExist(rev, path)
    return results

  def cat(self, rev, path):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'f':
      raise BadFileType(rev, path)
    cmd = [HG, 'cat', '-r', rev, path]
    return self._command(cmd)

  def _readlink(self, rev, path):
    cmd = [HG, 'cat', '-r', rev, path]
    return self._command(cmd)

  def readlink(self, rev, path):
    rev = type(self).cleanRev(rev)
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'l':
      raise BadFileType(rev, path)
    return self._readlink(rev, path)

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

  def log(self, revrange=None, path=None, follow=False, followfirst=False,
          prune=None, limit=None):
    cmd = [HG, 'log', '--debug', '--template={node}\n{parents}\n{date|hgdate}\n{author}\n:{desc|firstline}\n\n']
    if limit is not None:
      cmd.append('-l' + str(limit))
    if follow:
      cmd.append('--follow')
    if followfirst:
      cmd.append('--follow-first')
    if prune is not None:
      cmd.extend(['--prune', str(prune)])
    if revrange is None:
      pass
    elif isinstance(revrange, tuple):
      if revrange[0] is None:
        if revrange[1] is None:
          pass
        else:
          cmd.extend(['-r', ':' + revrange[1]])
      else:
        if revrange[1] is None:
          cmd.extend(['-r', revrange[0] + ':'])
        else:
          cmd.extend(['-r', revrange[0] + ':' + revrange[1]])
    else:
      cmd.extend(['-r', str(revrange)])
    if path:
      cmd.extend(['--', type(self).cleanPath(path)])
    output = self._command(cmd)

    results = []
    for log in output.split('\n\n')[:-1]:
      rev, parents, date, author, subject = log.split('\n', 4)
      parents = [x[1] for x in filter(lambda x: x[0] != '-1',
        (x.split(':') for x in parents.split()))]
      ts, tzoffset = date.split()
      date = datetime.datetime.fromtimestamp(float(ts))
      date = date.replace(tzinfo=UTCOffset(-int(tzoffset)/60))
      subject = subject[1:]
      results.append(CommitLogEntry(rev, parents, date, author, subject))
    return results

  def diff(self, rev_a, rev_b, path_a, path_b=None):
    raise NotImplementedError
