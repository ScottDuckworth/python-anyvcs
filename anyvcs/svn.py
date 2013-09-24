import collections
import fnmatch
import re
import subprocess
from common import *

SVNADMIN = 'svnadmin'
SVNLOOK = 'svnlook'

head_rev_rx = re.compile(r'^(?=.)(?P<head>\D[^:]*)?:?(?P<rev>\d+)?$')
mergeinfo_rx = re.compile(r'^(?P<head>.+):(?P<minrev>\d+)(?:-(?P<maxrev>\d+))$')
changed_copy_info_rx = re.compile(r'^    \(from (?P<path>.+):r(?P<rev>\d+)\)')

HistoryEntry = collections.namedtuple('HistoryEntry', 'rev path')
ChangeInfo = collections.namedtuple('ChangeInfo', 'status copy')

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

  def __init__(self, path):
    super(SvnRepo, self).__init__(path)
    self.branch_glob = ['/trunk/', '/branches/*/']
    self.tag_glob = ['/tags/*/']

  def _proplist(self, rev, path):
    cmd = [SVNLOOK, 'proplist', '-r', rev, '.', path or '--revprop']
    output = self._command(cmd)
    return [x.strip() for x in output.splitlines()]

  def proplist(self, rev, path=None):
    rev, prefix = self._maprev(rev)
    if path is None:
      return self._proplist(str(rev), None)
    else:
      path = type(self).cleanPath(prefix + path)
      return self._proplist(str(rev), path)

  def _propget(self, prop, rev, path):
    cmd = [SVNLOOK, 'propget', '-r', rev, '.', prop, path or '--revprop']
    return self._command(cmd)

  def propget(self, prop, rev, path=None):
    rev, prefix = self._maprev(rev)
    if path is None:
      return self._propget(prop, str(rev), None)
    else:
      path = type(self).cleanPath(prefix + path)
      return self._propget(prop, str(rev), path)

  def _mergeinfo(self, rev, path):
    revstr = str(rev)
    if 'svn:mergeinfo' not in self._proplist(revstr, path):
      return []
    results = []
    mergeinfo = self._propget('svn:mergeinfo', revstr, path)
    for line in mergeinfo.splitlines():
      m = mergeinfo_rx.match(line)
      assert m
      head, minrev, maxrev = m.group('head', 'minrev', 'maxrev')
      minrev = int(minrev)
      maxrev = int(maxrev or minrev)
      results.append((head, minrev, maxrev))
    return results

  def _maprev(self, rev):
    if isinstance(rev, int):
      return (rev, '/')
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

  def _heads(self, globs):
    root = {}
    for glob in globs:
      n = root
      for p in glob.strip('/').split('/'):
        n = n.setdefault(p, {})
    youngest = self.youngest()
    results = []
    def match(n, path):
      for d in self.ls(youngest, path):
        if d.type == 'd':
          for k, v in n.iteritems():
            if fnmatch.fnmatchcase(d.name, k):
              if path:
                p = path + '/' + d.name
              else:
                p = d.name
              if v:
                match(v, p)
              else:
                results.append(p)
    match(root, '')
    return results

  def branches(self):
    return self._heads(self.branch_glob)

  def tags(self):
    return self._heads(self.tag_glob)

  def heads(self):
    return ['HEAD'] + self._heads(self.branch_glob + self.tag_glob)

  def empty(self):
    cmd = [SVNLOOK, 'history', '.', '-l2']
    output = self._command(cmd)
    return len(output.splitlines()) < 4

  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    if revrange is None or revrange == (None, None):
      results = []
      for rev, prefix in self._history(self.youngest(), '/', limit):
        results.append(self._logentry(rev, prefix))
      return results
    elif isinstance(revrange, tuple):
      path_filter = None
      if revrange[1] is None:
        include = set()
        rev1 = self.youngest()
        for head in self.heads():
          if head == 'HEAD':
            continue
          prefix1 = type(self).cleanPath(head)
          include.update(self._mergehistory(rev1, prefix1))
      else:
        rev1, prefix1 = self._maprev(revrange[1])
        if firstparent:
          include = self._history(rev1, prefix1)
        else:
          include = self._mergehistory(rev1, prefix1)
        if path is not None:
          path_filter = set([(type(self).cleanPath(prefix1), 0, rev1)])
      if revrange[0] is None:
        results = include
      else:
        rev0, prefix0 = self._maprev(revrange[0])
        exclude = self._mergehistory(rev0, prefix0)
        results = include - exclude
      results = sorted(results, key=lambda x: x.rev, reverse=True)
      if path_filter is not None:
        path = type(self).cleanPath(path)
        _results = []
        for r in results:
          changed = self._changed(r.rev)
          merge = set()
          for prefix, minrev, maxrev in path_filter:
            if minrev <= r.rev <= maxrev:
              fullpath = prefix + path
              if fullpath in changed:
                mergeinfo = self._mergeinfo(r.rev, prefix)
                merge.update(mergeinfo)
                _results.append(r)
                continue
          path_filter.update(merge)
        results = _results
      if limit is not None:
        results = results[:limit]
      results = map(lambda x: self._logentry(x.rev, x.path), results)
      if merges is not None:
        if merges:
          results = filter(lambda x: len(x.parents) > 1, results)
        else:
          results = filter(lambda x: len(x.parents) <= 1, results)
      return results
    else:
      rev, prefix = self._maprev(revrange)
      h = self._history(rev, prefix, 1)
      rev = h[0].rev
      return self._logentry(rev, prefix)

  def _logentry(self, rev, path, history=None):
    revstr = str(rev)
    cmd = [SVNLOOK, 'info', '.', '-r', revstr]
    output = self._command(cmd)
    author, date, logsize, message = output.split('\n', 3)
    date = parse_isodate(date)
    if history is None:
      history = self._history(rev, path, 2)
    parents = []
    if len(history) > 1:
      prev = history[1].rev
      if path == '/':
        parents.append(prev)
      else:
        parents.append('%s:%d' % (path, prev))
      for head, minrev, maxrev in self._mergeinfo(rev, path):
        if prev < maxrev:
          h = self._history(maxrev, head, 1)
          if head == '/':
            parents.append(h[0].rev)
          else:
            parents.append('%s:%d' % (head, h[0].rev))
    return CommitLogEntry(rev, parents, date, author, message)

  def diff(self, rev_a, rev_b, path_a, path_b=None):
    raise NotImplementedError

  def _changed(self, rev):
    cmd = [SVNLOOK, 'changed', '.', '-r', str(rev), '--copy-info']
    output = self._command(cmd)
    lines = output.splitlines()
    lines.reverse()
    results = {}
    while lines:
      line = lines.pop()
      status = line[:3]
      path = '/' + line[4:].lstrip('/')
      copy = None
      if status.endswith('+'):
        line = lines.pop()
        m = changed_copy_info_rx.match(line)
        assert m
        rev, p = m.group('rev', 'path')
        p = '/' + path.lstrip('/')
        copy = HistoryEntry(int(rev), p)
      results[path] = ChangeInfo(status, copy)
    return results

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

  def _mergehistory(self, rev, path, limit=None):
    results = set(self._history(rev, path, limit))
    for head, minrev, maxrev in self._mergeinfo(rev, path):
      l = maxrev - minrev + 1
      if limit is not None:
        l = min(l, limit)
      h = self._history(maxrev, head, l)
      for r, p in h:
        if r < minrev:
          break
        results.add(HistoryEntry(r, p))
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

    for head, minrev, maxrev in self._mergeinfo(rev1, prefix1):
      for h in history2:
        if h.rev < minrev or h.rev < youngest.rev:
          break
        if h.path == head and minrev <= h.rev <= maxrev:
          youngest = h

    for head, minrev, maxrev in self._mergeinfo(rev2, prefix2):
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

    return None
