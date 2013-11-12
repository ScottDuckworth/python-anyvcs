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

import collections
import fnmatch
import re
import subprocess
from common import *

DIFF = 'diff'
SVN = 'svn'
SVNADMIN = 'svnadmin'
SVNLOOK = 'svnlook'

head_rev_rx = re.compile(r'^(?=.)(?P<head>\D[^:]*)?:?(?P<rev>\d+)?$')
mergeinfo_rx = re.compile(r'^(?P<head>.+):(?P<minrev>\d+)(?:-(?P<maxrev>\d+))$')
changed_copy_info_rx = re.compile(r'^[ ]{4}\(from (?P<src>.+)$\)')

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

  def __init__(self, path):
    super(SvnRepo, self).__init__(path)
    self.branch_glob = ['/trunk/', '/branches/*/']
    self.tag_glob = ['/tags/*/']

  @property
  def private_path(self):
    import os
    path = os.path.join(self.path, '.private')
    try:
      os.mkdir(path)
    except OSError as e:
      import errno
      if e.errno != errno.EEXIST:
        raise
    return path

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
      return (rev, '/')
    elif head == 'HEAD':
      return (rev, '/')
    else:
      return (rev, '/' + head)

  def canonical_rev(self, rev):
    if isinstance(rev, int):
      return rev
    elif isinstance(rev, (str, unicode)) and rev.isdigit():
      return int(rev)
    else:
      rev, prefix = self._maprev(rev)
      return rev

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    rev, prefix = self._maprev(rev)
    revstr = str(rev)
    path = type(self).cleanPath(prefix + path)
    forcedir = False
    if path.endswith('/'):
      forcedir = True
      if path != '/':
        path = path.rstrip('/')
    if path == '/':
      if directory:
        entry = attrdict(path='/', type='d')
        if 'commit' in report:
          entry.commit = self._history(revstr, '/', 1)[0].rev
        return [entry]
      ltrim = 1
      prefix = '/'
    else:
      ltrim = len(path) + 1
      prefix = path + '/'

    cmd = [SVNLOOK, 'tree', '-r', revstr, '--full-paths']
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
      entry = attrdict(path=name.strip('/'))
      if name.endswith('/'):
        if recursive and not recursive_dirs:
          continue
        entry.type = 'd'
        entry_name = entry_name.rstrip('/')
      else:
        proplist = self._proplist(revstr, name)
        if 'svn:special' in proplist:
          link = self._cat(revstr, name).split(None, 1)
          if len(link) == 2 and link[0] == 'link':
            entry.type = 'l'
            if 'target' in report:
              entry.target = link[1]
        if 'type' not in entry:
          entry.type = 'f'
          if 'executable' in report:
            entry.executable = 'svn:executable' in proplist
          if 'size' in report:
            entry.size = len(self._cat(revstr, name))
      if entry_name:
        entry.name = entry_name
      if 'commit' in report:
        entry.commit = self._history(revstr, name, 1)[0].rev
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
    if ls[0].get('type') != 'f':
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
    if ls[0].get('type') != 'l':
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
        if d.get('type') == 'd':
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
    return ['HEAD'] + self._heads(self.branch_glob)

  def tags(self):
    return self._heads(self.tag_glob)

  def heads(self):
    return ['HEAD'] + self._heads(self.branch_glob + self.tag_glob)

  def empty(self):
    cmd = [SVNLOOK, 'history', '.', '-l2']
    output = self._command(cmd)
    return len(output.splitlines()) < 4

  def __contains__(self, rev):
    rev, prefix = self._maprev(rev)
    cmd = [SVNLOOK, 'history', '.', prefix, '-l1', '-r', str(rev)]
    p = subprocess.Popen(cmd, cwd=self.path, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return p.returncode == 0

  def __len__(self):
    cmd = [SVNLOOK, 'history', '.']
    output = self._command(cmd)
    return len(output.splitlines()) - 3

  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    if not (revrange is None or isinstance(revrange, (tuple, list))):
      # a single revision was given
      rev, prefix = self._maprev(revrange)
      h = self._history(rev, prefix, 1)
      rev = h[0].rev
      return self._logentry(rev, prefix)

    if revrange is None:
      results = self._history(self.youngest(), path or '/', limit)
    else:
      if revrange[1] is None:
        include = set()
        rev1 = self.youngest()
        for head in self.heads():
          if head == 'HEAD':
            continue
          if path:
            p = head + '/' + path.lstrip('/')
          else:
            p = type(self).cleanPath(head)
          include.update(self._mergehistory(rev1, p, limit))
      else:
        rev1, prefix1 = self._maprev(revrange[1])
        if path:
          p = type(self).cleanPath(prefix1 + '/' + path)
        else:
          p = prefix1
        if firstparent:
          include = self._history(rev1, p)
        else:
          include = self._mergehistory(rev1, p, limit)

      if revrange[0] is None:
        results = include
      else:
        rev0, prefix0 = self._maprev(revrange[0])
        exclude = self._mergehistory(rev0, prefix0)
        results = include - exclude

      results = sorted(results, key=lambda x: x.rev, reverse=True)

    results = map(lambda x: self._logentry(x.rev, x.path), results)
    if merges is not None:
      if merges:
        results = filter(lambda x: len(x.parents) > 1, results)
      else:
        results = filter(lambda x: len(x.parents) <= 1, results)
    return results

  def _logentry(self, rev, path, history=None):
    import hashlib
    revstr = str(rev)
    cmd = [SVNLOOK, 'info', '.', '-r', revstr]
    cachekey = hashlib.sha1(revstr).hexdigest()
    entry = self._commit_cache.get(cachekey)
    if entry:
      return entry
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
    entry = CommitLogEntry(rev, parents, date, author, message)
    if cachekey not in self._commit_cache:
      self._commit_cache[cachekey] = entry
    return entry

  def pdiff(self, rev):
    rev, prefix = self._maprev(rev)
    if rev == 0:
      return ''
    cmd = [SVNLOOK, 'diff', '.', '-r', str(rev)]
    output = self._command(cmd)
    output = re.sub(r'^--- ', '--- a/', output, flags=re.M)
    output = re.sub(r'^\+\+\+ ', '+++ b/', output, flags=re.M)
    return output

  def diff(self, rev_a, rev_b, path=None):
    import os, shutil, tempfile
    rev_a, prefix_a = self._maprev(rev_a)
    rev_b, prefix_b = self._maprev(rev_b)
    tmpdir = tempfile.mkdtemp(prefix='anyvcs-svn-diff.')
    try:
      path_a = os.path.join(tmpdir, 'a')
      path_b = os.path.join(tmpdir, 'b')
      url_a = 'file://%s/%s@%d' % (self.path, prefix_a, rev_a)
      url_b = 'file://%s/%s@%d' % (self.path, prefix_b, rev_b)
      cmd = [SVN, 'export', '-q', url_a, path_a]
      subprocess.check_call(cmd)
      cmd = [SVN, 'export', '-q', url_b, path_b]
      subprocess.check_call(cmd)
      if path is None:
        cmd = [DIFF, '-urN', 'a', 'b']
      else:
        path = type(self).cleanPath(path)
        cmd = [DIFF, '-urN', 'a' + path, 'b' + path]
      p = subprocess.Popen(cmd, cwd=tmpdir, stdout=subprocess.PIPE)
      stdout, stderr = p.communicate()
      if p.returncode not in (0, 1):
        raise subprocess.CalledProcessError(p.returncode, cmd, stdout)
      return stdout
    finally:
      shutil.rmtree(tmpdir)

  def changed(self, rev):
    rev, prefix = self._maprev(rev)
    if rev == 0:
      return []
    cmd = [SVNLOOK, 'changed', '.', '-r', str(rev), '--copy-info']
    output = self._command(cmd)
    lines = output.splitlines()
    lines.reverse()
    results = []
    while lines:
      line = lines.pop()
      status = line[:3]
      path = line[4:].lstrip('/')
      copy = None
      if status.endswith('+'):
        line = lines.pop()
        m = changed_copy_info_rx.match(line)
        assert m
        copy = m.group('src')
      entry = FileChangeInfo(path, status, copy)
      results.append(entry)
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

  def _blame(self, rev, path):
    import os
    import xml.etree.ElementTree as ET
    url = 'file://' + os.path.abspath(self.path) + path
    cmd = [SVN, 'blame', '--xml', '-r', rev, url]
    output = self._command(cmd)
    tree = ET.fromstring(output)
    results = []
    cat = self._cat(rev, path)
    for entry, text in zip(tree.find('target').iter('entry'), cat.splitlines()):
      commit = entry.find('commit')
      rev = int(commit.attrib.get('revision'))
      author = commit.find('author').text
      date = commit.find('date').text
      date = parse_isodate(date)
      results.append(blame_tuple(rev, author, date, text))
    return results

  def blame(self, rev, path):
    rev, prefix = self._maprev(rev)
    path = type(self).cleanPath(prefix + path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].get('type') != 'f':
      raise BadFileType(rev, path)
    return self._blame(str(rev), path)

  def dump(self, stream, progress=None, lower=None, upper=None,
           incremental=False, deltas=False):
    """Dump the repository to a dumpfile stream.

    Arguments:
    stream    A file stream to which the dumpfile is written
    progress  A file stream to which progress is written

    See `svnadmin help dump' for details on the other arguments.

    """
    cmd = [SVNADMIN, 'dump', '.']
    if progress is None:
      cmd.append('-q')
    if lower is not None:
      cmd.append('-r')
      if upper is None:
        cmd.append(str(int(lower)))
      else:
        cmd.append('%d:%d' % (int(lower), int(upper)))
    if incremental:
      cmd.append('--incremental')
    if deltas:
      cmd.append('--deltas')
    p = subprocess.Popen(cmd, cwd=self.path, stdout=stream, stderr=progress)
    p.wait()
    if p.returncode != 0:
      raise subprocess.CalledProcessError(p.returncode, cmd)

  def load(self, stream, progress=None, ignore_uuid=False, force_uuid=False,
           use_pre_commit_hook=False, use_post_commit_hook=False,
           parent_dir=None):
    """Load a dumpfile stream into the repository.

    Arguments:
    stream    A file stream from which the dumpfile is read
    progress  A file stream to which progress is written

    See `svnadmin help load' for details on the other arguments.

    """
    cmd = [SVNADMIN, 'load', '.']
    if progress is None:
      cmd.append('-q')
    if ignore_uuid:
      cmd.append('--ignore-uuid')
    if force_uuid:
      cmd.append('--force-uuid')
    if use_pre_commit_hook:
      cmd.append('--use-pre-commit-hook')
    if use_post_commit_hook:
      cmd.append('--use-post-commit-hook')
    if parent_dir:
      cmd.extend(['--parent-dir', parent_dir])
    p = subprocess.Popen(cmd, cwd=self.path, stdin=stream,
                         stdout=progress, stderr=subprocess.PIPE)
    stderr = p.stderr.read()
    p.wait()
    if p.returncode != 0:
      raise subprocess.CalledProcessError(p.returncode, cmd, stderr)
