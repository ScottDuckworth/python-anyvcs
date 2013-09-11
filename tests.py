import anyvcs
import os
import shutil
import subprocess
import tempfile
import unittest
from anyvcs import UnknownVCSType, PathDoesNotExist, BadFileType

logfile = open(os.devnull, 'w')

def check_call(args, **kwargs):
  logfile.write('%s\n' % repr(args))
  kwargs.setdefault('stdout', logfile)
  kwargs.setdefault('stderr', logfile)
  subprocess.check_call(args, **kwargs)

def normalize_ls(x):
  return sorted(x, key=lambda y: y.get('name'))

def normalize_heads(x):
  return sorted(x)

class GitTest(unittest.TestCase):
  head = 'master'

  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test-git.')
    main_path = os.path.join(cls.dir, 'main')
    working_path = os.path.join(cls.dir, 'work')
    cls.repo = anyvcs.create(main_path, 'git')
    check_call(['git', 'clone', main_path, working_path])
    for message in cls.setUpWorkingCopy(working_path):
      check_call(['git', 'add', '.'], cwd=working_path)
      check_call(['git', 'commit', '-m', message], cwd=working_path)
    check_call(['git', 'push', 'origin', 'master'], cwd=working_path)

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.dir)

class HgTest(unittest.TestCase):
  head = 'default'

  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test-hg.')
    main_path = os.path.join(cls.dir, 'main')
    working_path = os.path.join(cls.dir, 'work')
    cls.repo = anyvcs.create(main_path, 'hg')
    check_call(['hg', 'clone', main_path, working_path])
    for message in cls.setUpWorkingCopy(working_path):
      check_call(['hg', 'add', '.'], cwd=working_path)
      check_call(['hg', 'commit', '-m', message], cwd=working_path)
    check_call(['hg', 'push'], cwd=working_path)

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.dir)

class SvnTest(unittest.TestCase):
  head = 0

  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test-svn.')
    main_path = os.path.join(cls.dir, 'main')
    working_path = os.path.join(cls.dir, 'work')
    cls.repo = anyvcs.create(main_path, 'svn')
    check_call(['svn', 'checkout', 'file://' + main_path, working_path])
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
    for message in cls.setUpWorkingCopy(working_path):
      os.path.walk(working_path, add, working_path)
      check_call(['svn', 'commit', '-m', message], cwd=working_path)
      cls.head += 1

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.dir)


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
