import anyvcs
import datetime
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from anyvcs import UnknownVCSType, PathDoesNotExist, BadFileType
from anyvcs.common import CommitLogEntry, UTCOffset

logfile = open(os.devnull, 'w')
date_rx = re.compile(r'^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?:\s+|T)(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})(?:\.(?P<us>\d{6}))?(?:Z|\s+(?P<tz>[+-]?\d{4}))$')

UTC = UTCOffset(0, 'UTC')

def check_call(args, **kwargs):
  logfile.write('%s\n' % repr(args))
  kwargs.setdefault('stdout', logfile)
  kwargs.setdefault('stderr', logfile)
  subprocess.check_call(args, **kwargs)

def check_output(args, **kwargs):
  logfile.write('%s\n' % repr(args))
  kwargs.setdefault('stderr', logfile)
  return subprocess.check_output(args, **kwargs)

def normalize_ls(x):
  return sorted(x, key=lambda y: y.get('name'))

def normalize_heads(x):
  return sorted(x)

def normalize_datetime(x):
  return x.astimezone(UTC).replace(microsecond=0)

def normalize_logmsg(x):
  return x.rstrip()

def parse_date(x):
  m = date_rx.match(x)
  if m is None:
    return None
  d = datetime.datetime(*[int(x) for x in m.group('year', 'month', 'day', 'hour', 'minute', 'second')])
  if m.group('us'):
    d = d.replace(microsecond=int(m.group('us')))
  tz = m.group('tz')
  if tz:
    offset = datetime.timedelta(minutes=int(tz[-2:]), hours=int(tz[-4:-2]))
    if tz[0] == '-':
      offset = -offset
  else:
    offset = 0
  d = d.replace(tzinfo=UTCOffset(offset))
  return d

class VCSTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.commits = []
    cls.zerocommit = None
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test.')
    cls.main_path = os.path.join(cls.dir, 'main')
    cls.working_path = os.path.join(cls.dir, 'work')

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.dir)

  def assertCommitLogEqual(self, a, b):
    self.assertEqual(a.rev, b.rev)
    self.assertEqual(a.parents, b.parents)
    self.assertEqual(normalize_datetime(a.date), normalize_datetime(b.date), '%s != %s' % (a.date, b.date))
    self.assertEqual(a.author, b.author)
    self.assertEqual(a.subject, b.subject)

class GitTest(VCSTest):
  head = 'master'

  @classmethod
  def setUpClass(cls):
    VCSTest.setUpClass()
    cls.repo = anyvcs.create(cls.main_path, 'git')
    check_call(['git', 'clone', cls.main_path, cls.working_path])
    for message in cls.setUpWorkingCopy(cls.working_path):
      check_call(['git', 'add', '.'], cwd=cls.working_path)
      check_call(['git', 'commit', '-m', message], cwd=cls.working_path)
      rev = check_output(['git', 'log', '-n1', '--pretty=format:%H'], cwd=cls.working_path)
      parents = check_output(['git', 'log', '-n1', '--pretty=format:%P'], cwd=cls.working_path).split()
      output = check_output(['git', 'log', '-n1', '--pretty=format:%ai'], cwd=cls.working_path)
      date = parse_date(output)
      author = check_output(['git', 'log', '-n1', '--pretty=format:%an <%ae>'], cwd=cls.working_path)
      subject = check_output(['git', 'log', '-n1', '--pretty=format:%s'], cwd=cls.working_path)
      entry = CommitLogEntry(rev, parents, date, author, subject)
      cls.commits.insert(0, entry)
    check_call(['git', 'push', 'origin', 'master'], cwd=cls.working_path)

class HgTest(VCSTest):
  head = 'default'

  @classmethod
  def setUpClass(cls):
    VCSTest.setUpClass()
    cls.repo = anyvcs.create(cls.main_path, 'hg')
    check_call(['hg', 'clone', cls.main_path, cls.working_path])
    for message in cls.setUpWorkingCopy(cls.working_path):
      check_call(['hg', 'add', '.'], cwd=cls.working_path)
      check_call(['hg', 'commit', '-m', message], cwd=cls.working_path)
      rev = check_output(['hg', 'log', '-l1', '--template={node}'], cwd=cls.working_path)
      parents = []
      output = check_output(['hg', 'log', '-l1', '--template={parents}', '--debug'], cwd=cls.working_path)
      for p in output.split():
        r,node = p.split(':')
        if r != '-1':
          parents.append(node)
      output = check_output(['hg', 'log', '-l1', '--template={date|isodatesec}'], cwd=cls.working_path)
      date = parse_date(output)
      author = check_output(['hg', 'log', '-l1', '--template={author}'], cwd=cls.working_path)
      subject = check_output(['hg', 'log', '-l1', '--template={desc|firstline}'], cwd=cls.working_path)
      entry = CommitLogEntry(rev, parents, date, author, subject)
      cls.commits.insert(0, entry)
    check_call(['hg', 'push'], cwd=cls.working_path)

class SvnTest(VCSTest):
  head = 0

  @classmethod
  def setUpClass(cls):
    import xml.etree.ElementTree as ET

    VCSTest.setUpClass()
    cls.zerocommit = 0
    cls.repo = anyvcs.create(cls.main_path, 'svn')
    check_call(['svn', 'checkout', 'file://' + cls.main_path, cls.working_path])
    def add(top, dirname, fnames):
      import stat
      dirname = os.path.relpath(dirname, top)
      if '.svn' in fnames:
        del fnames[fnames.index('.svn')]
      for fname in fnames:
        p = os.path.join(dirname, fname)
        check_call(['svn', 'add', '-q', '--force', p], cwd=top)
        st = os.lstat(os.path.join(top, p))
        if stat.S_ISREG(st.st_mode) and stat.S_IXUSR & st.st_mode:
          check_call(['svn', 'propset', 'svn:executable', 'yes', p], cwd=top)
    for message in cls.setUpWorkingCopy(cls.working_path):
      os.path.walk(cls.working_path, add, cls.working_path)
      check_call(['svn', 'commit', '-m', message], cwd=cls.working_path)
      check_call(['svn', 'update'], cwd=cls.working_path)
      xml = check_output(['svn', 'log', '-l1', '--xml'], cwd=cls.working_path)
      root = ET.fromstring(xml)
      logentry = root.find('logentry')
      rev = int(logentry.attrib.get('revision'))
      parents = [rev-1]
      date = parse_date(logentry.find('date').text)
      author = logentry.find('author').text
      subject = logentry.find('msg').text.split('\n', 1)[0]
      entry = CommitLogEntry(rev, parents, date, author, subject)
      cls.commits.insert(0, entry)
      cls.head += 1


class BasicTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    with open(os.path.join(working_path, 'a'), 'w') as f:
      f.write('Pisgah')
    os.chmod(os.path.join(working_path, 'a'), 0644)
    os.symlink('a', os.path.join(working_path, 'b'))
    os.mkdir(os.path.join(working_path, 'c'))
    os.mkdir(os.path.join(working_path, 'c', 'd'))
    with open(os.path.join(working_path, 'c', 'd', 'e'), 'w') as f:
      f.write('Denali')
    os.chmod(os.path.join(working_path, 'c', 'd', 'e'), 0755)
    os.symlink('e', os.path.join(working_path, 'c', 'd', 'f'))
    yield 'commit 1'

  def test_ls1(self):
    result = self.repo.ls(self.head, '')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls2(self):
    result = self.repo.ls(self.head, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls3(self):
    result = self.repo.ls(self.head, '/a')
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls4(self):
    result = self.repo.ls(self.head, '/b')
    correct = [{'type':'l'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls5(self):
    result = self.repo.ls(self.head, '/c')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls6(self):
    result = self.repo.ls(self.head, '/c/')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls7(self):
    result = self.repo.ls(self.head, '/c', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls8(self):
    result = self.repo.ls(self.head, '/c/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls9(self):
    result = self.repo.ls(self.head, '/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls10(self):
    result = self.repo.ls(self.head, '/a', directory=True)
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.head, '/z')

  def test_ls_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.head, '/a/')

  def test_ls_recursive(self):
    result = self.repo.ls(self.head, '/', recursive=True)
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c/d/e', 'type':'f'},
      {'name':'c/d/f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_recursive_dirs(self):
    result = self.repo.ls(self.head, '/', recursive=True, recursive_dirs=True)
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
      {'name':'c/d', 'type':'d'},
      {'name':'c/d/e', 'type':'f'},
      {'name':'c/d/f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_size(self):
    result = self.repo.ls(self.head, '/', report=('size',))
    correct = [
      {'name':'a', 'type':'f', 'size':6},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_target(self):
    result = self.repo.ls(self.head, '/', report=('target',))
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l', 'target':'a'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable1(self):
    result = self.repo.ls(self.head, '/', report=('executable',))
    correct = [
      {'name':'a', 'type':'f', 'executable':False},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable2(self):
    result = self.repo.ls(self.head, '/c/d', report=('executable',))
    correct = [
      {'name':'e', 'type':'f', 'executable':True},
      {'name':'f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_cat1(self):
    result = self.repo.cat(self.head, 'a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat2(self):
    result = self.repo.cat(self.head, '/a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat3(self):
    result = self.repo.cat(self.head, 'c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat4(self):
    result = self.repo.cat(self.head, '/c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.head, '/z')

  def test_cat_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.head, '/a/')

  def test_cat_error3(self):
    self.assertRaises(BadFileType, self.repo.cat, self.head, '/b')

  def test_cat_error4(self):
    self.assertRaises(BadFileType, self.repo.cat, self.head, '/c')

  def test_readlink1(self):
    result = self.repo.readlink(self.head, 'b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink2(self):
    result = self.repo.readlink(self.head, '/b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink3(self):
    result = self.repo.readlink(self.head, 'c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink4(self):
    result = self.repo.readlink(self.head, '/c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.head, '/z')

  def test_readlink_error2(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.head, '/a')

  def test_readlink_error3(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.head, '/b/')

  def test_readlink_error4(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.head, '/c')

  def test_log1(self):
    result = self.repo.log(revrange=self.head)
    correct = self.commits[0]
    self.assertIsInstance(result, CommitLogEntry)
    self.assertCommitLogEqual(result, correct)

  def test_log2(self):
    result = self.repo.log()
    correct = self.commits
    self.assertGreaterEqual(len(result), len(correct))
    for result_i, correct_i in zip(result, correct):
      self.assertCommitLogEqual(result_i, correct_i)

  def test_log3(self):
    result = self.repo.log(revrange=(self.zerocommit, None))
    correct = self.commits
    self.assertEqual(len(result), len(correct), 'len(%s) != len(%s)' % (result, correct))
    for result_i, correct_i in zip(result, correct):
      self.assertCommitLogEqual(result_i, correct_i)

  def test_log4(self):
    result = self.repo.log(revrange=(self.zerocommit, self.head))
    correct = self.commits
    self.assertEqual(len(result), len(correct), 'len(%s) != len(%s)' % (result, correct))
    for result_i, correct_i in zip(result, correct):
      self.assertCommitLogEqual(result_i, correct_i)

  def test_log5(self):
    result = self.repo.log(limit=1)
    correct = self.commits[0:1]
    self.assertEqual(len(result), 1)
    for result_i, correct_i in zip(result, correct):
      self.assertCommitLogEqual(result_i, correct_i)


class BasicGitTest(GitTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['master']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['master',]
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

class BasicHgTest(HgTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['default']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = ['tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_bookmarks(self):
    result = self.repo.bookmarks()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['default', 'tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

class BasicSvnTest(SvnTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['HEAD']
    self.assertEqual(result, correct)

if __name__ == '__main__':
  unittest.main()
