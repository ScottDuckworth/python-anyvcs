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

import anyvcs
import datetime
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from abc import ABCMeta, abstractmethod
from anyvcs.common import CommitLogEntry, UTCOffset, UnknownVCSType, PathDoesNotExist, BadFileType

debug_to_stdout = False
keep_test_dir = False

if debug_to_stdout:
  import sys
  logfile = sys.stdout
else:
  logfile = open(os.devnull, 'w')

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


### VCS FRAMEWORK CLASSES ###

class VCSTest(unittest.TestCase):
  __metaclass__ = ABCMeta

  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test.')
    if keep_test_dir:
      print cls.dir
    cls.main_path = os.path.join(cls.dir, 'main')
    cls.working_path = os.path.join(cls.dir, 'work')
    cls.working_head = None
    cls.setUpRepos()

  @classmethod
  def setUpRepos(cls):
    raise NotImplementedError

  @classmethod
  def getAbsoluteRev(cls):
    raise NotImplementedError

  @classmethod
  def export(cls, rev, path):
    raise NotImplementedError

  @classmethod
  def tearDownClass(cls):
    if not keep_test_dir:
      shutil.rmtree(cls.dir)

  @classmethod
  def check_call(cls, *args, **kwargs):
    kwargs.setdefault('cwd', cls.working_path)
    check_call(*args, **kwargs)

  @classmethod
  def check_output(cls, *args, **kwargs):
    kwargs.setdefault('cwd', cls.working_path)
    return check_output(*args, **kwargs)

  @classmethod
  def encode_branch(cls, s):
    return s

  @classmethod
  def decode_branch(cls, s):
    return s

  @classmethod
  def encode_tag(cls, s):
    return s

  @classmethod
  def decode_tag(cls, s):
    return s

class GitTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'git')
    check_call(['git', 'clone', cls.main_path, cls.working_path])
    cls.main_branch = 'master'
    cls.working_head = 'master'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doGit(cls)

  @classmethod
  def getAbsoluteRev(cls):
    try:
      return cls.check_output(['git', 'log', '-1', '--pretty=format:%H'])
    except subprocess.CalledProcessError:
      return None

  @classmethod
  def export(cls, rev, path):
    os.mkdir(path)
    cmd1 = ['git', 'archive', rev]
    data = check_output(cmd1, cwd=cls.main_path)
    cmd2 = ['tar', '-x', '-C', path]
    p = subprocess.Popen(cmd2, stdin=subprocess.PIPE)
    p.communicate(data)
    if p.returncode != 0:
      raise subprocess.CalledProcessError(p.returncode, cmd2)

class HgTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'hg')
    check_call(['hg', 'clone', cls.main_path, cls.working_path])
    cls.main_branch = 'default'
    cls.working_head = 'default'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doHg(cls)

  @classmethod
  def getAbsoluteRev(cls):
    return cls.check_output(['hg', 'log', '-l1', '--template={node}'])

  @classmethod
  def export(cls, rev, path):
    check_call(['hg', 'archive', '-r', str(rev), path], cwd=cls.main_path)
    trash = os.path.join(path, '.hg_archival.txt')
    if os.path.exists(trash):
      os.unlink(trash)

class SvnTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'svn')
    check_call(['svn', 'checkout', 'file://' + cls.main_path, cls.working_path])
    cls.main_branch = 'HEAD'
    cls.working_head = 'HEAD'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doSvn(cls)

  @classmethod
  def getAbsoluteRev(cls):
    xml = cls.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    rev = tree.find('entry').attrib.get('revision')
    if cls.working_head == 'HEAD':
      return int(rev)
    else:
      return '/%s:%s' % (cls.encode_branch(cls.working_head), rev)

  @classmethod
  def export(cls, rev, path):
    rev, prefix = cls.repo._maprev(rev)
    url = 'file://%s/%s@%d' % (cls.main_path, prefix, rev)
    check_call(['svn', 'export', url, path])

  @classmethod
  def encode_branch(cls, s):
    if s == 'trunk':
      return s
    return 'branches/' + s

  @classmethod
  def decode_branch(cls, s):
    if s == 'trunk':
      return s
    assert s.startswith('branches/')
    return s[9:]

  @classmethod
  def encode_tag(cls, s):
    return 'tags/' + s

  @classmethod
  def decode_tag(cls, s):
    assert s.startswith('tags/')
    return s[5:]


class Action(object):
  __metaclass__ = ABCMeta

  @abstractmethod
  def doGit(self, test):
    raise NotImplementedError

  @abstractmethod
  def doHg(self, test):
    raise NotImplementedError

  @abstractmethod
  def doSvn(self, test):
    raise NotImplementedError

class CreateStandardDirectoryStructure(Action):
  """Create the standard directory structure, if any"""

  def doGit(self, test):
    pass

  def doHg(self, test):
    pass

  def doSvn(self, test):
    test.check_call(['svn', 'mkdir', 'trunk', 'branches', 'tags'])
    commit = Commit('create standard directory structure')
    commit.doSvn(test)
    shutil.rmtree(test.working_path)
    url = 'file://'+test.main_path+'/trunk'
    check_call(['svn', 'co', url, test.working_path])
    test.main_branch = 'trunk'
    test.working_head = 'trunk'

class Commit(Action):
  """Commit and push"""

  def __init__(self, message):
    self.message = message

  def doGit(self, test):
    test.check_call(['git', 'add', '-A', '.'])
    test.check_call(['git', 'commit', '-m', self.message])
    test.check_call(['git', 'push', '--set-upstream', 'origin', test.working_head])
    time.sleep(1) # git has a 1 second granularity, this keeps logs in order

  def doHg(self, test):
    test.check_call(['hg', 'addremove'])
    test.check_call(['hg', 'commit', '-m', self.message])
    test.check_call(['hg', 'push', '--new-branch', '-b', test.working_head])

  def doSvn(self, test):
    xml = test.check_output(['svn', 'status', '--xml'])
    tree = ET.fromstring(xml)
    for entry in tree.iter('entry'):
      test.check_call(['svn', 'add', '--force', '-q', entry.attrib.get('path')])
    test.check_call(['svn', 'commit', '-m', self.message])
    test.check_call(['svn', 'update'])

class BranchAction(Action):
  def __init__(self, name):
    self.name = name

class CreateBranch(BranchAction):
  """Create a new branch based on the current branch and switch to it"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', '-b', self.name])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'branch', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    xml = test.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    url1 = tree.find('entry').find('url').text
    url2 = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'copy', url1, url2, '-m', 'create branch ' + self.name])
    test.check_call(['svn', 'switch', url2])
    test.working_head = self.name

class CreateUnrelatedBranch(BranchAction):
  """Create a new branch unrelated to any other branch and switch to it"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', '--orphan', self.name])
    test.check_call(['git', 'rm', '-rf', '.'])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'update', 'null'])
    test.check_call(['hg', 'branch', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'mkdir', url, '-m', 'create branch ' + self.name])
    shutil.rmtree(test.working_path)
    check_call(['svn', 'co', url, test.working_path])
    test.working_head = self.name

class DeleteBranch(BranchAction):
  """Delete/close a branch and push"""

  def doGit(self, test):
    test.check_call(['git', 'branch', '-d', self.name])
    test.check_call(['git', 'push', 'origin', ':' + self.name])

  def doHg(self, test):
    test.check_call(['hg', 'update', self.name])
    test.check_call(['hg', 'commit', '--close-branch', '-m', 'close branch ' + self.name])
    test.check_call(['hg', 'push'])
    test.check_call(['hg', 'update', test.working_head])

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'delete', url, '-m', 'delete branch ' + self.name])

class SwitchBranch(BranchAction):
  """Switch working copy to another branch"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', self.name])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'update', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'switch', url])
    test.working_head = self.name

class Merge(BranchAction):
  """Merge and push"""

  def doGit(self, test):
    test.check_call(['git', 'merge', '--no-ff', self.name])
    test.check_call(['git', 'push', 'origin', test.working_head])
    time.sleep(1) # git has a 1 second granularity, this keeps logs in order

  def doHg(self, test):
    test.check_call(['hg', 'merge', self.name])
    test.check_call(['hg', 'commit', '-m', 'merge from %s to %s' % (self.name, test.working_head)])
    test.check_call(['hg', 'push'])

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'merge', url])
    test.check_call(['svn', 'commit', '-m', 'merge from %s to %s' % (self.name, test.working_head)])

class ReintegrateMerge(Merge):
  """Merge and push"""

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'merge', '--reintegrate', url])
    test.check_call(['svn', 'commit', '-m', 'reintegrate merge from %s to %s' % (self.name, test.working_head)])

class CreateTag(Action):
  """Create tag and push"""

  def __init__(self, name):
    self.name = name

  def doGit(self, test):
    test.check_call(['git', 'tag', self.name, '-m', 'create tag ' + self.name])
    test.check_call(['git', 'push', 'origin', self.name])

  def doHg(self, test):
    test.check_call(['hg', 'tag', self.name, '-m', 'create tag ' + self.name])
    test.check_call(['hg', 'push'])

  def doSvn(self, test):
    xml = test.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    url1 = tree.find('entry').find('url').text
    url2 = 'file://' + test.main_path + '/' + test.encode_tag(self.name)
    test.check_call(['svn', 'copy', url1, url2, '-m', 'create tag ' + self.name])


### TEST CASE: EmptyTest ###

class EmptyTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    return
    yield

  def test_empty(self):
    result = self.repo.empty()
    correct = True
    self.assertEqual(result, correct)

  def test_len(self):
    result = len(self.repo)
    correct = 0
    self.assertEqual(result, correct)

  def test_private_path(self):
    private_path = self.repo.private_path
    self.assertTrue(os.path.isdir(private_path))
    self.assertEqual(os.listdir(private_path), [])

class GitEmptyTest(GitTest, EmptyTest):
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
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 0)

class HgEmptyTest(HgTest, EmptyTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
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
    correct = ['tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 0)

class SvnEmptyTest(SvnTest, EmptyTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['HEAD']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0].rev, 0)


### TEST CASE: BasicTest ###

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
    yield Commit('commit 1\n\nsetup working copy')
    cls.rev1 = cls.getAbsoluteRev()

  def test_empty(self):
    result = self.repo.empty()
    correct = False
    self.assertEqual(result, correct)

  def test_ls1(self):
    result = self.repo.ls(self.main_branch, '')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls2(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls3(self):
    result = self.repo.ls(self.main_branch, '/a')
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls4(self):
    result = self.repo.ls(self.main_branch, '/b')
    correct = [{'type':'l'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls5(self):
    result = self.repo.ls(self.main_branch, '/c')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls6(self):
    result = self.repo.ls(self.main_branch, '/c/')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls7(self):
    result = self.repo.ls(self.main_branch, '/c', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls8(self):
    result = self.repo.ls(self.main_branch, '/c/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls9(self):
    result = self.repo.ls(self.main_branch, '/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls10(self):
    result = self.repo.ls(self.main_branch, '/a', directory=True)
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.main_branch, '/z')

  def test_ls_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.main_branch, '/a/')

  def test_ls_recursive(self):
    result = self.repo.ls(self.main_branch, '/', recursive=True)
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c/d/e', 'type':'f'},
      {'name':'c/d/f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_recursive_dirs(self):
    result = self.repo.ls(self.main_branch, '/', recursive=True, recursive_dirs=True)
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
    result = self.repo.ls(self.main_branch, '/', report=('size',))
    correct = [
      {'name':'a', 'type':'f', 'size':6},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_target(self):
    result = self.repo.ls(self.main_branch, '/', report=('target',))
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l', 'target':'a'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable1(self):
    result = self.repo.ls(self.main_branch, '/', report=('executable',))
    correct = [
      {'name':'a', 'type':'f', 'executable':False},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable2(self):
    result = self.repo.ls(self.main_branch, '/c/d', report=('executable',))
    correct = [
      {'name':'e', 'type':'f', 'executable':True},
      {'name':'f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_cat1(self):
    result = self.repo.cat(self.main_branch, 'a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat2(self):
    result = self.repo.cat(self.main_branch, '/a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat3(self):
    result = self.repo.cat(self.main_branch, 'c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat4(self):
    result = self.repo.cat(self.main_branch, '/c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.main_branch, '/z')

  def test_cat_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.main_branch, '/a/')

  def test_cat_error3(self):
    self.assertRaises(BadFileType, self.repo.cat, self.main_branch, '/b')

  def test_cat_error4(self):
    self.assertRaises(BadFileType, self.repo.cat, self.main_branch, '/c')

  def test_cat_error5(self):
    self.assertRaises(BadFileType, self.repo.cat, self.main_branch, '/')

  def test_readlink1(self):
    result = self.repo.readlink(self.main_branch, 'b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink2(self):
    result = self.repo.readlink(self.main_branch, '/b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink3(self):
    result = self.repo.readlink(self.main_branch, 'c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink4(self):
    result = self.repo.readlink(self.main_branch, '/c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.main_branch, '/z')

  def test_readlink_error2(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.main_branch, '/a')

  def test_readlink_error3(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.main_branch, '/b/')

  def test_readlink_error4(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.main_branch, '/c')

  def test_readlink_error5(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.main_branch, '/')

  def test_log_head(self):
    result = self.repo.log(revrange=self.main_branch)
    self.assertIsInstance(result, CommitLogEntry)
    self.assertEqual(result.rev, self.rev1)

  def test_log_rev(self):
    result = self.repo.log(revrange=self.rev1)
    self.assertIsInstance(result, CommitLogEntry)
    self.assertEqual(result.rev, self.rev1)

  def test_in(self):
    self.assertIn(self.rev1, self.repo)

  def test_not_in(self):
    self.assertNotIn('foo', self.repo)

  def test_len(self):
    result = len(self.repo)
    correct = 1
    self.assertEqual(result, correct)

  def test_pdiff(self):
    import errno
    empty_path = os.path.join(self.dir, 'empty')
    rev1_path = os.path.join(self.dir, 'rev1')
    try:
      shutil.rmtree(empty_path)
    except OSError as e:
      if e.errno != errno.ENOENT:
        raise
    try:
      shutil.rmtree(rev1_path)
    except OSError as e:
      if e.errno != errno.ENOENT:
        raise
    os.mkdir(empty_path)
    self.export(self.rev1, rev1_path)
    pdiff = self.repo.pdiff(self.rev1)
    p = subprocess.Popen(['patch', '-p1', '-s'], cwd=empty_path, stdin=subprocess.PIPE)
    p.communicate(pdiff)
    self.assertEqual(p.returncode, 0)
    # symlinks are not reconstructed by patch, so just make sure the file exists
    # then remove it so that diff works
    self.assertTrue(os.path.isfile(os.path.join(empty_path, 'b')))
    os.unlink(os.path.join(empty_path, 'b'))
    os.unlink(os.path.join(rev1_path, 'b'))
    self.assertTrue(os.path.isfile(os.path.join(empty_path, 'c', 'd', 'f')))
    os.unlink(os.path.join(empty_path, 'c', 'd', 'f'))
    os.unlink(os.path.join(rev1_path, 'c', 'd', 'f'))
    rc = subprocess.call(['diff', '-urN', empty_path, rev1_path])
    self.assertEqual(rc, 0)

  def test_blame(self):
    result = self.repo.blame(self.main_branch, 'a')
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0].rev, self.rev1)
    self.assertIsInstance(result[0].author, str)
    self.assertIsInstance(result[0].date, datetime.datetime)
    self.assertEqual(result[0].line, 'Pisgah')

class GitBasicTest(GitTest, BasicTest):
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

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 1)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)

class HgBasicTest(HgTest, BasicTest):
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

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 1)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)

class SvnBasicTest(SvnTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['HEAD']
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 2)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)


### TEST CASE: UnrelatedBranchTest ###

class UnrelatedBranchTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    yield CreateStandardDirectoryStructure()
    with open(os.path.join(working_path, 'a'), 'w') as f:
      f.write('spoon')
    yield Commit('modify a')
    yield CreateUnrelatedBranch('branch1')
    with open(os.path.join(working_path, 'b'), 'w') as f:
      f.write('fish')
    yield Commit('modify b')

  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_ancestor(self):
    result = self.repo.ancestor(
      self.encode_branch(self.main_branch),
      self.encode_branch('branch1'))
    correct = None
    self.assertEqual(result, correct)

  def test_main_ls(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [{'name':'a', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_branch1_ls(self):
    result = self.repo.ls(self.encode_branch('branch1'), '/')
    correct = [{'name':'b', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

class GitUnrelatedBranchTest(GitTest, UnrelatedBranchTest): pass
class HgUnrelatedBranchTest(HgTest, UnrelatedBranchTest): pass
class SvnUnrelatedBranchTest(SvnTest, UnrelatedBranchTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD'] + map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))


### TEST CASES: BranchTest* ###

def setup_branch_test(test, step):
  """Setup a typical branching scenario for testing.

  step rev tree    branch     message
     1   1   *     (main)     standard directory structure
     2   2   *     (main)     modify a
     3   3   |\*   (branch1)  create branch1
         4   | *   (branch1)  modify b
     4   5   * |   (main)     modify c
     5   6 */| |   (branch2)  create branch2
         7 * | |   (branch2)  modify c
     6   8 | |\*   (branch1)  merge from main to branch1
     7   9 | | |\* (branch1a) create branch1a
        10 | | | * (branch1a) modify b
     8  11 | | */| (branch1)  reintegrate branch1a into branch1
     9  12 |\* | | (main)     reintegrate branch2 into main
    10  13 | |\* | (branch1)  merge from main to branch1
    11  14 | | * | (branch1)  modify a
    12  15 | */| | (main)     reintegrate branch1 into main
    13  16 X | | | (branch2)  delete branch2
        17   | | X (branch1a) delete branch1a
        18   | X   (branch1)  delete branch1

  """
  a_path = os.path.join(test.working_path, 'a')
  b_path = os.path.join(test.working_path, 'b')
  c_path = os.path.join(test.working_path, 'c')

  test.rev = {}

  if step < 1: return
  yield CreateStandardDirectoryStructure()
  test.rev[1] = test.getAbsoluteRev()

  if step < 2: return
  with open(a_path, 'w') as f: f.write('step 2')
  yield Commit('2: modify a')
  test.rev[2] = test.getAbsoluteRev()

  if step < 3: return
  yield CreateBranch('branch1')
  test.rev[3] = test.getAbsoluteRev()
  with open(b_path, 'w') as f: f.write('step 3')
  yield Commit('4: modify b')
  test.rev[4] = test.getAbsoluteRev()

  if step < 4: return
  yield SwitchBranch(test.main_branch)
  with open(c_path, 'w') as f: f.write('step 4')
  yield Commit('5: modify c')
  test.rev[5] = test.getAbsoluteRev()

  if step < 5: return
  yield CreateBranch('branch2')
  test.rev[6] = test.getAbsoluteRev()
  with open(c_path, 'w') as f: f.write('step 5')
  yield Commit('7: modify c')
  test.rev[7] = test.getAbsoluteRev()

  if step < 6: return
  yield SwitchBranch('branch1')
  yield Merge(test.main_branch)
  test.rev[8] = test.getAbsoluteRev()

  if step < 7: return
  yield CreateBranch('branch1a')
  test.rev[9] = test.getAbsoluteRev()
  with open(b_path, 'w') as f: f.write('step 7')
  yield Commit('10: modify b')
  test.rev[10] = test.getAbsoluteRev()

  if step < 8: return
  yield SwitchBranch('branch1')
  yield ReintegrateMerge('branch1a')
  test.rev[11] = test.getAbsoluteRev()

  if step < 9: return
  yield SwitchBranch(test.main_branch)
  yield ReintegrateMerge('branch2')
  test.rev[12] = test.getAbsoluteRev()

  if step < 10: return
  yield SwitchBranch('branch1')
  yield Merge(test.main_branch)
  test.rev[13] = test.getAbsoluteRev()

  if step < 11: return
  with open(a_path, 'w') as f: f.write('step 11')
  yield Commit('14: modify a')
  test.rev[14] = test.getAbsoluteRev()

  if step < 12: return
  yield SwitchBranch(test.main_branch)
  yield ReintegrateMerge('branch1')
  test.rev[15] = test.getAbsoluteRev()

  if step < 13: return
  yield DeleteBranch('branch2')
  test.rev[16] = test.getAbsoluteRev()
  yield DeleteBranch('branch1a')
  test.rev[17] = test.getAbsoluteRev()
  yield DeleteBranch('branch1')
  test.rev[18] = test.getAbsoluteRev()

### TEST CASE: BranchTestStep3 ###

class BranchTestStep3(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 3):
      yield action
    cls.revrev = {}
    for k in sorted(cls.rev.iterkeys()):
      cls.revrev.setdefault(cls.rev[k], k)

  def test_ancestor_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ancestor(self.main_branch, branch1)
    correct = self.rev[2]
    self.assertEqual(result, correct)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [{'name':'a', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 2')

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 3')

class GitLikeBranchTestStep3(BranchTestStep3):
  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 2
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.revrev[self.repo.log(revrange=branch1).rev]
    correct = 4
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [2]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1))]
    correct = [4, 2]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [4]
    self.assertEqual(result, correct)

class GitBranchTestStep3(GitTest, GitLikeBranchTestStep3): pass
class HgBranchTestStep3(HgTest, GitLikeBranchTestStep3): pass
class SvnBranchTestStep3(SvnTest, BranchTestStep3):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD'] + map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.repo.log(revrange=self.main_branch).rev
    correct = 2
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.log(revrange=branch1).rev
    correct = 4
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [x.rev for x in self.repo.log()]
    correct = range(4, -1, -1)
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = range(2, 0, -1)
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
    correct = range(4, 0, -1)
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = range(4, 2, -1)
    self.assertEqual(result, correct)

### TEST CASE: BranchTestStep7 ###

class BranchTestStep7(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 7):
      yield action
    cls.revrev = {}
    for k in sorted(cls.rev.iterkeys()):
      cls.revrev.setdefault(cls.rev[k], k)

  def test_ancestor_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ancestor(self.main_branch, branch1)
    correct = self.rev[5]
    self.assertEqual(result, correct)

  def test_ancestor_main_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ancestor(self.main_branch, branch1a)
    correct = self.rev[5]
    self.assertEqual(result, correct)

  def test_ancestor_main_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.ancestor(self.main_branch, branch2)
    correct = self.rev[5]
    self.assertEqual(result, correct)

  def test_ancestor_branch1_branch1a(self):
    branch1 = self.encode_branch('branch1')
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ancestor(branch1, branch1a)
    correct = self.rev[8]
    self.assertEqual(result, correct)

  def test_ancestor_branch1a_branch2(self):
    branch1a = self.encode_branch('branch1a')
    branch2 = self.encode_branch('branch2')
    result = self.repo.ancestor(branch1a, branch2)
    correct = self.rev[5]
    self.assertEqual(result, correct)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(self.main_branch, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 3')
    result = self.repo.cat(branch1, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ls(branch1a, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1a, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1a, '/b')
    self.assertEqual(result, 'step 7')
    result = self.repo.cat(branch1a, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.ls(branch2, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch2, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch2, '/c')
    self.assertEqual(result, 'step 5')

  def test_diff_main_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    path_a = os.path.join(self.dir, 'diff_main_branch1a_a')
    path_b = os.path.join(self.dir, 'diff_main_branch1a_b')
    self.export(self.main_branch, path_a)
    self.export(branch1a, path_b)
    diff = self.repo.diff(self.main_branch, branch1a)
    p = subprocess.Popen(['patch', '-p1', '-s'], cwd=path_a, stdin=subprocess.PIPE)
    p.communicate(diff)
    self.assertEqual(p.returncode, 0)
    rc = subprocess.call(['diff', '-urN', path_a, path_b])
    self.assertEqual(rc, 0)

class GitLikeBranchTestStep7(BranchTestStep7):
  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch,
                  [self.main_branch, 'branch1', 'branch1a', 'branch2'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 5
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.revrev[self.repo.log(revrange=branch1).rev]
    correct = 8
    self.assertEqual(result, correct)

  def test_log_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.revrev[self.repo.log(revrange=branch1a).rev]
    correct = 10
    self.assertEqual(result, correct)

  def test_log_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.revrev[self.repo.log(revrange=branch2).rev]
    correct = 7
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [5, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1))]
    correct = [8, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1_firstparent(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1), firstparent=True)]
    correct = [8, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch2))]
    correct = [7, 5, 2]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [8, 4]
    self.assertEqual(result, correct)

  def test_log_main_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch1a))]
    correct = [10, 8, 4]
    self.assertEqual(result, correct)

  def test_log_main_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch2))]
    correct = [7]
    self.assertEqual(result, correct)

class GitBranchTestStep7(GitTest, GitLikeBranchTestStep7): pass
class HgBranchTestStep7(HgTest, GitLikeBranchTestStep7): pass
class SvnBranchTestStep7(SvnTest, BranchTestStep7):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD'] + map(self.encode_branch,
                  [self.main_branch, 'branch1', 'branch1a', 'branch2'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.repo.log(revrange=self.main_branch).rev
    correct = 5
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.log(revrange=branch1).rev
    correct = 8
    self.assertEqual(result, correct)

  def test_log_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.repo.log(revrange=branch1a).rev
    correct = 10
    self.assertEqual(result, correct)

  def test_log_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.log(revrange=branch2).rev
    correct = 7
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [x.rev for x in self.repo.log()]
    correct = range(10, -1, -1)
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [5, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
    correct = [8, 5, 4, 3, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1_firstparent(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1), firstparent=True)]
    correct = [8, 4, 3, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = [x.rev for x in self.repo.log(revrange=(None, branch2))]
    correct = [7, 6, 5, 2, 1]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [8, 4, 3]
    self.assertEqual(result, correct)

  def test_log_main_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1a))]
    correct = [10, 9, 8, 4, 3]
    self.assertEqual(result, correct)

  def test_log_main_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch2))]
    correct = [7, 6]
    self.assertEqual(result, correct)

### TEST CASE: BranchTestStep9 ###

class BranchTestStep9(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 9):
      yield action
    cls.revrev = {}
    for k in sorted(cls.rev.iterkeys()):
      cls.revrev.setdefault(cls.rev[k], k)

  def test_ancestor_main_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.ancestor(self.main_branch, branch2)
    correct = self.rev[7]
    self.assertEqual(result, correct)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(self.main_branch, '/c')
    self.assertEqual(result, 'step 5')

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 7')
    result = self.repo.cat(branch1, '/c')
    self.assertEqual(result, 'step 4')

class GitLikeBranchTestStep9(BranchTestStep9):
  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 12
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.revrev[self.repo.log(revrange=branch1).rev]
    correct = 11
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [12, 7, 5, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1))]
    correct = [11, 10, 8, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [11, 10, 8, 4]
    self.assertEqual(result, correct)

class GitBranchTestStep9(GitTest, GitLikeBranchTestStep9): pass
class HgBranchTestStep9(HgTest, GitLikeBranchTestStep9): pass
class SvnBranchTestStep9(SvnTest, BranchTestStep9):
  def test_log_main(self):
    result = self.repo.log(revrange=self.main_branch).rev
    correct = 12
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.log(revrange=branch1).rev
    correct = 11
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [x.rev for x in self.repo.log()]
    correct = range(12, -1, -1)
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [12, 7, 6, 5, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
    correct = [11, 10, 9, 8, 5, 4, 3, 2, 1]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [11, 10, 9, 8, 4, 3]
    self.assertEqual(result, correct)

### TEST CASE: BranchTestStep11 ###

class BranchTestStep11(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 11):
      yield action
    cls.revrev = {}
    for k in sorted(cls.rev.iterkeys()):
      cls.revrev.setdefault(cls.rev[k], k)

  def test_ancestor_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ancestor(self.main_branch, branch1)
    correct = self.rev[12]
    self.assertEqual(result, correct)

  def test_ancestor_branch1_branch2(self):
    branch1 = self.encode_branch('branch1')
    branch2 = self.encode_branch('branch2')
    result = self.repo.ancestor(branch1, branch2)
    correct = self.rev[7]
    self.assertEqual(result, correct)

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 11')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 7')
    result = self.repo.cat(branch1, '/c')
    self.assertEqual(result, 'step 5')

class GitLikeBranchTestStep11(BranchTestStep11):
  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 12
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.revrev[self.repo.log(revrange=branch1).rev]
    correct = 14
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [12, 7, 5, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1))]
    correct = [14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1_onlymerges(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1), merges=True)]
    correct = [13, 12, 11, 8]
    self.assertEqual(result, correct)

  def test_log_None_branch1_nomerges(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1), merges=False)]
    correct = [14, 10, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_branch1_path_b(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, branch1), path='/b')]
    correct = [10, 4]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [14, 13, 11, 10, 8, 4]
    self.assertEqual(result, correct)

class GitBranchTestStep11(GitTest, GitLikeBranchTestStep11): pass
class HgBranchTestStep11(HgTest, GitLikeBranchTestStep11): pass
class SvnBranchTestStep11(SvnTest, BranchTestStep11):
  def test_log_main(self):
    result = self.repo.log(revrange=self.main_branch).rev
    correct = 12
    self.assertEqual(result, correct)

  def test_log_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.log(revrange=branch1).rev
    correct = 14
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [x.rev for x in self.repo.log()]
    correct = range(14, -1, -1)
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [12, 7, 6, 5, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
    correct = [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1_onlymerges(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1), merges=True)]
    correct = [13, 12, 11, 8]
    self.assertEqual(result, correct)

  def test_log_None_branch1_nomerges(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1), merges=False)]
    correct = [14, 10, 9, 7, 6, 5, 4, 3, 2, 1]
    self.assertEqual(result, correct)

  def test_log_None_branch1_path_b(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(None, branch1), path='/b')]
    correct = [11, 10, 4]
    self.assertEqual(result, correct)

  def test_log_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
    correct = [14, 13, 11, 10, 9, 8, 4, 3]
    self.assertEqual(result, correct)

### TEST CASE: BranchTestStep13 ###

class BranchTestStep13(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 13):
      yield action
    cls.revrev = {}
    for k in sorted(cls.rev.iterkeys()):
      cls.revrev.setdefault(cls.rev[k], k)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 11')
    result = self.repo.cat(self.main_branch, '/b')
    self.assertEqual(result, 'step 7')
    result = self.repo.cat(self.main_branch, '/c')
    self.assertEqual(result, 'step 5')

class GitBranchTestStep13(GitTest, BranchTestStep13):
  def test_branches(self):
    result = self.repo.branches()
    correct = [self.encode_branch(self.main_branch)]
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 15
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main_path_b(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch), path='/b')]
    correct = [10, 4]
    self.assertEqual(result, correct)

class HgBranchTestStep13(HgTest, BranchTestStep13):
  def test_branches(self):
    result = self.repo.branches()
    correct = [self.encode_branch(self.main_branch)]
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.revrev[self.repo.log(revrange=self.main_branch).rev]
    correct = 15
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [self.revrev[x.rev] for x in self.repo.log()]
    correct = [18, 17, 16, 15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = [15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
    self.assertEqual(result, correct)

  def test_log_None_main_path_b(self):
    result = [self.revrev[x.rev] for x in self.repo.log(revrange=(None, self.main_branch), path='/b')]
    correct = [10, 4]
    self.assertEqual(result, correct)

class SvnBranchTestStep13(SvnTest, BranchTestStep13):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['HEAD', self.encode_branch(self.main_branch)]
    self.assertEqual(sorted(result), sorted(correct))

  def test_log_main(self):
    result = self.repo.log(revrange=self.main_branch).rev
    correct = 15
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = [x.rev for x in self.repo.log()]
    correct = range(18, -1, -1)
    self.assertEqual(result, correct)

  def test_log_None_main(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
    correct = range(15, 0, -1)
    self.assertEqual(result, correct)

  def test_log_None_main_path_b(self):
    result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch), path='/b')]
    correct = [15, 11, 10, 4]
    self.assertEqual(result, correct)


if __name__ == '__main__':
  unittest.main()
