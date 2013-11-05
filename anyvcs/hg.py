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
import re
import subprocess
from common import *

HG = 'hg'

manifest_rx = re.compile(r'^(?P<mode>[0-7]{3}) (?P<type>.) (?P<name>.+)$')
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
  @classmethod
  def create(cls, path):
    cmd = [HG, 'init', path]
    subprocess.check_call(cmd)
    return cls(path)

  @property
  def private_path(self):
    import os
    path = os.path.join(self.path, '.hg', '.private')
    try:
      os.mkdir(path)
    except OSError as e:
      import errno
      if e.errno != errno.EEXIST:
        raise
    return path

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

    cmd = [HG, 'manifest', '-v', '-r', rev]
    output = self._command(cmd)
    dirs = set()
    exists = False
    for line in output.splitlines():
      m = manifest_rx.match(line)
      assert m, 'unexpected output: ' + line
      t, name = m.group('type', 'name')
      if name.startswith(prefix) or (not forcedir and name == path):
        if directory and name.startswith(prefix):
          yield ('d', '')
          return
        exists = True
        entry_name = name[ltrim:]
        if '/' in entry_name:
          p = parent_dirs(entry_name)
          if not recursive:
            d = p.next()
            if d not in dirs:
              dirs.add(d)
              yield ('d', d)
            continue
          if recursive_dirs:
            for d in p:
              if d not in dirs:
                dirs.add(d)
                yield ('d', d)
        yield (t, entry_name)
    if not exists:
      raise PathDoesNotExist(rev, path)

  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    revstr = str(rev)
    path = type(self).cleanPath(path)
    if path == '':
      if directory:
        return [{'type':'d'}]

    if True and 'commit' in report:
      import tempfile
      with tempfile.NamedTemporaryFile() as style:
        style.write(
          r"changeset = '{rev}\n{node}\n{files}\0'" '\n'
          r"file = '{file|escape}\n'" '\n'
        )
        style.flush()
        cmd = [HG, 'log', '--style', style.name, '-r', 'reverse(ancestors('+revstr+'))']
        log = self._command(cmd).split('\0')
    else:
      log = None

    results = []
    for t, name in self._ls(revstr, path, recursive, recursive_dirs, directory):
      entry = attrdict()
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
        p = type(self).cleanPath(path + '/' + name)
        if log is None:
          cmd = [HG, 'log', '--template={node}', '-l1', '-r', 'reverse(ancestors('+revstr+'))', '--', p]
          entry.commit = self._command(cmd)
        else:
          for logentry in log:
            lines = logentry.splitlines()
            found = False
            for l in lines[2:]:
              if l == p or l.startswith(p+'/'):
                found = True
                break
            if found:
              entry.commit = lines[1]
              break
      results.append(entry)
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
      if single:
        return entry
      results.append(entry)
    return results

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
      results.append(blame_tuple(rev, author, date, text))
    return results

  def blame(self, rev, path):
    path = type(self).cleanPath(path)
    ls = self.ls(rev, path, directory=True)
    assert len(ls) == 1
    if ls[0].get('type') != 'f':
      raise BadFileType(rev, path)
    return self._blame(str(rev), path)
