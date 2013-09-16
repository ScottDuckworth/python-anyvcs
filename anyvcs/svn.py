import collections
import re
import subprocess
from common import *

SVNADMIN = 'svnadmin'
SVNLOOK = 'svnlook'

head_rev_rx = re.compile(r'^(?=.)(?P<head>\D[^:]*)?:?(?P<rev>\d+)?$')
mergeinfo_rx = re.compile(r'^(?P<head>.+):(?P<minrev>\d+)(?:-(?P<maxrev>\d+))$')

HistoryEntry = collections.namedtuple('HistoryEntry', 'rev path')

class SvnRepo(VCSRepo):
  @classmethod
  def create(cls, path):
    cmd = [SVNADMIN, 'create', path]
    subprocess.check_call(cmd)
    return cls(path)

  @classmethod
  def cleanPath(cls, path):
    path = multislash_rx.sub('/', path)
    if not path.startswith('/'):
      path = '/' + path
    return path

  def _proplist(self, rev, path):
    cmd = [SVNLOOK, 'proplist', '-r', rev, '.', path or '--revprop']
    output = self._command(cmd)
    return [x.strip() for x in output.splitlines()]

  def proplist(self, rev, path=None):
    rev, prefix = self._maprev(rev)
    if path is None:
      return self._proplist(rev, None)
    else:
      path = type(self).cleanPath(prefix + path)
      return self._proplist(rev, path)

  def _propget(self, prop, rev, path):
    cmd = [SVNLOOK, 'propget', '-r', rev, '.', prop, path or '--revprop']
    return self._command(cmd)

  def propget(self, prop, rev, path=None):
    rev, prefix = self._maprev(rev)
    if path is None:
      return self._propget(prop, rev, None)
    else:
      path = type(self).cleanPath(prefix + path)
      return self._propget(prop, rev, path)

  def _maprev(self, rev):
    if isinstance(rev, int):
      return (rev, '')
    m = head_rev_rx.match(rev)
    assert m, 'invalid rev'
    head, rev = m.group('head', 'rev')
    if rev:
      rev = int(rev)
    else:
      rev = self.youngest()
    if head is None:
      return (rev, '')
    elif head == 'HEAD':
      return (rev, '')
    else:
      return (rev, '/' + head)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    rev, prefix = self._maprev(rev)
    path = type(self).cleanPath(prefix + path)
    forcedir = False
    if path.endswith('/'):
      forcedir = True
      if path != '/':
        path = path.rstrip('/')
    if path == '/':
      if directory:
        return [{'type':'d'}]
      ltrim = 1
      prefix = '/'
    else:
      ltrim = len(path) + 1
      prefix = path + '/'

    cmd = [SVNLOOK, 'tree', '-r', str(rev), '--full-paths']
    if not recursive:
      cmd.append('--non-recursive')
    cmd.extend(['.', path])
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    output, stderr = p.communicate()
    if p.returncode != 0:
      if p.returncode == 1 and 'File not found' in stderr:
        raise PathDoesNotExist(rev, path)
      raise subprocess.CalledProcessError(p.returncode, cmd, stderr)

    results = []
    lines = output.splitlines()
    if forcedir and not lines[0].endswith('/'):
      raise PathDoesNotExist(rev, path)
    if lines[0].endswith('/'):
      if directory:
        lines = lines[:1]
      else:
        lines = lines[1:]
    for name in lines:
      entry_name = name[ltrim:]
      entry = attrdict()
      if name.endswith('/'):
        if recursive and not recursive_dirs:
          continue
        entry.type = 'd'
        entry_name = entry_name.rstrip('/')
      else:
        proplist = self._proplist(str(rev), name)
        if 'svn:special' in proplist:
          link = self._cat(str(rev), name).split(None, 1)
          if len(link) == 2 and link[0] == 'link':
            entry.type = 'l'
            if 'target' in report:
              entry.target = link[1]
        if 'type' not in entry:
          entry.type = 'f'
          if 'executable' in report:
            entry.executable = 'svn:executable' in proplist
          if 'size' in report:
            entry.size = len(self._cat(str(rev), name))
      if entry_name:
        entry.name = entry_name
      results.append(entry)
    return results

  def _cat(self, rev, path):
    cmd = [SVNLOOK, 'cat', '-r', rev, '.', path]
    return self._command(cmd)

  def cat(self, rev, path):
    rev, prefix = self._maprev(rev)
    path = type(self).cleanPath(prefix + path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'f':
      raise BadFileType(rev, path)
    return self._cat(str(rev), path)

  def _readlink(self, rev, path):
    output = self._cat(rev, path)
    link = output.split(None, 1)
    assert len(link) == 2 and link[0] == 'link'
    return link[1]

  def readlink(self, rev, path):
    rev, prefix = self._maprev(rev)
    path = type(self).cleanPath(prefix + path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].type != 'l':
      raise BadFileType(rev, path)
    return self._readlink(str(rev), path)

  def youngest(self):
    cmd = [SVNLOOK, 'youngest', '.']
    return int(self._command(cmd))

  def _heads(self, headdirs):
    youngest = self.youngest()
    root = self.ls(youngest, '/')
    if {'name':'trunk', 'type':'d'} in root:
      roots = [('', root)]
    else:
      roots = []
      for d in (x.name for x in filter(lambda x: x.type == 'd', root)):
        droot = self.ls(youngest, '/' + d + '/')
        if {'name':'trunk', 'type':'d'} in droot:
          roots.append((d+'/', droot))
    results = []
    for prefix, root in roots:
      results.append(prefix + 'trunk')
      for d in headdirs:
        if {'name':d, 'type':'d'} in root:
          dls = self.ls(self.youngest(), '/' + prefix + d + '/')
          results.extend(prefix + d + '/' + x.name
                         for x in filter(lambda x: x.type == 'd', dls))
    return results

  def branches(self):
    return self._heads(('branches',))

  def tags(self):
    return self._heads(('tags',))

  def heads(self):
    return ['HEAD'] + self._heads(('branches', 'tags'))

  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    if revrange is None:
      revrange = (None, None)
    single = False
    if isinstance(revrange, tuple):
      if revrange[0] is None:
        startrev = None
      else:
        startrev = int(revrange[0])
      if revrange[1] is None:
        endrev = self.youngest()
      else:
        endrev = int(revrange[1])
      cmd = [SVNLOOK, 'history', '.', '-r', str(endrev)]
      if limit is not None:
        cmd.extend(['-l', str(limit)])
      elif startrev is not None:
        cmd.extend(['-l', str(endrev - startrev)])
      output = self._command(cmd)

      revs = []
      consume = endrev is None
      for line in output.splitlines()[2:]:
        rev = int(line.split()[0])
        if not consume and rev != endrev:
          continue
        consume = True
        if rev == startrev:
          break
        revs.append(rev)
    else:
      revs = [int(revrange)]
      single = True

    results = []
    for rev in revs:
      cmd = [SVNLOOK, 'info', '.', '-r', str(rev)]
      output = self._command(cmd)
      author, date, logsize, message = output.split('\n', 3)
      if rev == 0:
        parents = []
      else:
        parents = [rev - 1]
      date = parse_isodate(date)
      subject = message.split('\n', 1)[0]
      entry = CommitLogEntry(rev, parents, date, author, subject)
      if single:
        return entry
      results.append(entry)
    return results

  def diff(self, rev_a, rev_b, path_a, path_b=None):
    raise NotImplementedError

  def _history(self, rev, path, limit=None):
    cmd = [SVNLOOK, 'history', '.', '-r', str(rev), path]
    if limit is not None:
      cmd.extend(['-l', str(limit)])
    output = self._command(cmd)
    results = []
    for line in output.splitlines()[2:]:
      r, p = line.split(None, 1)
      results.append(HistoryEntry(int(r), p))
    return results

  def ancestor(self, rev1, rev2):
    rev1, prefix1 = self._maprev(rev1)
    rev2, prefix2 = self._maprev(rev2)
    prefix1 = type(self).cleanPath(prefix1)
    if prefix1 != '/':
      prefix1 = prefix1.rstrip('/')
    prefix2 = type(self).cleanPath(prefix2)
    if prefix2 != '/':
      prefix2 = prefix2.rstrip('/')

    self.ls(rev1, prefix1, directory=True)
    self.ls(rev2, prefix2, directory=True)

    minrev = min(rev1, rev2)
    if prefix1 == prefix2:
      return '%s:%d' % (prefix1, minrev)

    history1 = self._history(minrev, prefix1)
    history2 = self._history(minrev, prefix2)

    youngest = HistoryEntry(0, '/')

    if 'svn:mergeinfo' in self._proplist(str(rev1), prefix1):
      mergeinfo = self._propget('svn:mergeinfo', str(rev1), prefix1)
      for line in mergeinfo.splitlines():
        m = mergeinfo_rx.match(line)
        assert m
        head, minrev, maxrev = m.group('head', 'minrev', 'maxrev')
        minrev = int(minrev)
        maxrev = int(maxrev or minrev)
        for h in history2:
          if h.rev < minrev or h.rev < youngest.rev:
            break
          if h.path == head and minrev <= h.rev <= maxrev:
            youngest = h

    if 'svn:mergeinfo' in self._proplist(str(rev2), prefix2):
      mergeinfo = self._propget('svn:mergeinfo', str(rev2), prefix2)
      for line in mergeinfo.splitlines():
        m = mergeinfo_rx.match(line)
        assert m
        head, minrev, maxrev = m.group('head', 'minrev', 'maxrev')
        minrev = int(minrev)
        maxrev = int(maxrev or minrev)
        for h in history1:
          if h.rev < minrev or h.rev < youngest.rev:
            break
          if h.path == head and minrev <= h.rev <= maxrev:
            youngest = h

    if youngest.rev > 0:
      return '%s:%d' % (youngest.path, youngest.rev)

    i1 = 0
    i2 = 0
    len1 = len(history1)
    len2 = len(history2)
    while i1 < len1 and i2 < len2:
      if history1[i1].rev < history2[i2].rev:
        i2 += 1
      elif history1[i1].rev > history2[i2].rev:
        i1 += 1
      else:
        if history1[i1].path == history2[i2].path:
          return '%s:%d' % (history1[i1].path, history1[i1].rev)
        else:
          i1 += 1
          i2 += 1

    return 0
