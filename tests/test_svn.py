# Copyright (c) 2013-2014, Clemson University
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name Clemson University nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import common
import anyvcs
from anyvcs.common import CommitLogEntry

import datetime
import getpass
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET


class SvnTest(common.VCSTest):
    vcs = 'svn'

    @classmethod
    def setUpRepos(cls):
        cls.repo = anyvcs.create(cls.main_path, 'svn')
        common.check_call(['svn', 'checkout', 'file://' + cls.main_path, cls.working_path])
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
            return '%s:%s' % (cls.encode_branch(cls.working_head), rev)

    @classmethod
    def export(cls, rev, path):
        rev, prefix = cls.repo._maprev(rev)
        url = 'file://%s/%s@%d' % (cls.main_path, prefix, rev)
        common.check_call(['svn', 'export', url, path])

    @classmethod
    def encode_branch(cls, s):
        if s == 'trunk':
            return 'trunk'
        return 'branches/' + s

    @classmethod
    def decode_branch(cls, s):
        if s == 'trunk':
            return 'trunk'
        assert s.startswith('branches/')
        return s[9:]

    @classmethod
    def encode_tag(cls, s):
        return 'tags/' + s

    @classmethod
    def decode_tag(cls, s):
        assert s.startswith('tags/')
        return s[5:]

    @classmethod
    def branch_prefix(cls, branch):
        if branch == 'trunk':
            return 'trunk/'
        return 'branches/' + branch + '/'


class SvnEmptyTest(SvnTest, common.EmptyTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = ['HEAD']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_log(self):
        result = self.repo.log()
        self.assertEqual(1, len(result))
        self.assertEqual(0, result[0].rev)

    def test_changed(self):
        result = self.repo.changed(0)
        correct = []
        self.assertEqual(correct, result)

    def test_pdiff(self):
        path_a = os.path.join(self.dir, 'empty')
        path_b = os.path.join(self.dir, 'pdiff')
        shutil.rmtree(path_a, ignore_errors=True)
        shutil.rmtree(path_b, ignore_errors=True)
        os.mkdir(path_a)
        self.export(0, path_b)
        pdiff = self.repo.pdiff(0)
        p = subprocess.Popen(['patch', '-p1', '-s'], cwd=path_a, stdin=subprocess.PIPE)
        p.communicate(pdiff)
        self.assertEqual(0, p.returncode)
        rc = subprocess.call(['diff', '-urN', path_a, path_b])
        self.assertEqual(0, rc)


class SvnEmptyWithCommitsTest(SvnTest, common.EmptyWithCommitsTest):
    pass


class SvnMismatchedFileTypeTest(SvnTest, common.MismatchedFileTypeTest):
    pass


class SvnBasicTest(SvnTest, common.BasicTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = ['HEAD']
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = self.repo.log()
        self.assertIsInstance(result, list)
        self.assertEqual(2, len(result))
        self.assertIsInstance(result[0], CommitLogEntry)
        self.assertEqual(self.rev1, result[0].rev)
        self.assertIsInstance(result[0].date, datetime.datetime)

    def test_log_single(self):
        result1 = self.repo.log(revrange=1, limit=1)
        result2 = self.repo.log(revrange='1', limit=1)
        self.assertEqual(result1.parents, result2.parents)
        self.assertEqual(result1.parents, [0])

    def test_changed(self):
        result = self.repo.changed(self.rev1)
        correct = ['a', 'b', 'c/', 'c/d/', 'c/d/e', 'c/d/f']
        self.assertEqual(correct, sorted(x.path for x in result))
        for x in result:
            self.assertIsInstance(x.status, str)
            self.assertLessEqual(1, len(x.status))

    def test_blame(self):
        result = self.repo.blame(self.main_branch, 'a')
        self.assertIsInstance(result, list)
        self.assertEqual(1, len(result))
        self.assertEqual(self.rev1, result[0].rev)
        self.assertEqual(getpass.getuser(), result[0].author)
        self.assertIsInstance(result[0].date, datetime.datetime)
        self.assertEqual('Pisgah'.encode(), result[0].line)

    def test_proplist(self):
        result = self.repo.proplist(self.rev1)
        expected = sorted(['svn:log', 'svn:author', 'svn:date'])
        self.assertEqual(expected, sorted(result))

    def test_proplist_path(self):
        result = self.repo.proplist(self.rev1, 'a')
        expected = []
        self.assertEqual(expected, result)

    def test_compose_rev1(self):
        result = self.repo.compose_rev(self.main_branch, self.rev1)
        expected = '%s:%d' % (self.main_branch, self.rev1)
        self.assertEqual(expected, result)

    def test_compose_rev2(self):
        rev = '%s:%d' % (self.main_branch, self.rev1)
        result = self.repo.compose_rev(self.main_branch, rev)
        expected = rev
        self.assertEqual(expected, result)


class SvnUnrelatedBranchTest(SvnTest, common.UnrelatedBranchTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD'] + list(map(self.encode_branch, [self.main_branch, 'branch1']))
        self.assertEqual(sorted(correct), sorted(result))


class SvnBranchTestStep3(SvnTest, common.BranchTestStep3):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD'] + list(map(self.encode_branch, [self.main_branch, 'branch1']))
        self.assertEqual(sorted(correct), sorted(result))

    def test_log_main(self):
        result = self.repo.log(revrange=self.main_branch).rev
        correct = 2
        self.assertEqual(correct, result)

    def test_log_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = self.repo.log(revrange=branch1).rev
        correct = 4
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = [x.rev for x in self.repo.log()]
        correct = list(range(4, -1, -1))
        self.assertEqual(correct, result)

    def test_log_None_main(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
        correct = list(range(2, 0, -1))
        self.assertEqual(correct, result)

    def test_log_None_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
        correct = list(range(4, 0, -1))
        self.assertEqual(correct, result)

    def test_log_main_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
        correct = list(range(4, 2, -1))
        self.assertEqual(correct, result)

class SvnBranchTestStep7(SvnTest, common.BranchTestStep7):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD'] + list(map(
            self.encode_branch,
            [self.main_branch, 'branch1', 'branch1a', 'branch2']
        ))
        self.assertEqual(sorted(correct), sorted(result))

    def test_log_main(self):
        result = self.repo.log(revrange=self.main_branch).rev
        correct = 5
        self.assertEqual(correct, result)

    def test_log_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = self.repo.log(revrange=branch1).rev
        correct = 8
        self.assertEqual(correct, result)

    def test_log_branch1a(self):
        branch1a = self.encode_branch('branch1a')
        result = self.repo.log(revrange=branch1a).rev
        correct = 10
        self.assertEqual(correct, result)

    def test_log_branch2(self):
        branch2 = self.encode_branch('branch2')
        result = self.repo.log(revrange=branch2).rev
        correct = 7
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = [x.rev for x in self.repo.log()]
        correct = list(range(10, -1, -1))
        self.assertEqual(correct, result)

    def test_log_None_main(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
        correct = [5, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
        correct = [8, 5, 4, 3, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1_firstparent(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1), firstparent=True)]
        correct = [8, 4, 3, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch2(self):
        branch2 = self.encode_branch('branch2')
        result = [x.rev for x in self.repo.log(revrange=(None, branch2))]
        correct = [7, 6, 5, 2, 1]
        self.assertEqual(correct, result)

    def test_log_main_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
        correct = [8, 4, 3]
        self.assertEqual(correct, result)

    def test_log_main_branch1a(self):
        branch1a = self.encode_branch('branch1a')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1a))]
        correct = [10, 9, 8, 4, 3]
        self.assertEqual(correct, result)

    def test_log_main_branch2(self):
        branch2 = self.encode_branch('branch2')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch2))]
        correct = [7, 6]
        self.assertEqual(correct, result)


class SvnBranchTestStep9(SvnTest, common.BranchTestStep9):
    def test_log_main(self):
        result = self.repo.log(revrange=self.main_branch).rev
        correct = 12
        self.assertEqual(correct, result)

    def test_log_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = self.repo.log(revrange=branch1).rev
        correct = 11
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = [x.rev for x in self.repo.log()]
        correct = list(range(12, -1, -1))
        self.assertEqual(correct, result)

    def test_log_None_main(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
        correct = [12, 7, 6, 5, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
        correct = [11, 10, 9, 8, 5, 4, 3, 2, 1]
        self.assertEqual(correct, result)

    def test_log_main_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
        correct = [11, 10, 9, 8, 4, 3]
        self.assertEqual(correct, result)


class SvnBranchTestStep11(SvnTest, common.BranchTestStep11):
    def test_log_main(self):
        result = self.repo.log(revrange=self.main_branch).rev
        correct = 12
        self.assertEqual(correct, result)

    def test_log_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = self.repo.log(revrange=branch1).rev
        correct = 14
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = [x.rev for x in self.repo.log()]
        correct = list(range(14, -1, -1))
        self.assertEqual(correct, result)

    def test_log_None_main(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
        correct = [12, 7, 6, 5, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1))]
        correct = [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1_onlymerges(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1), merges=True)]
        correct = [13, 12, 11, 8]
        self.assertEqual(correct, result)

    def test_log_None_branch1_nomerges(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1), merges=False)]
        correct = [14, 10, 9, 7, 6, 5, 4, 3, 2, 1]
        self.assertEqual(correct, result)

    def test_log_None_branch1_path_b(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(None, branch1), path='/b')]
        correct = [11, 4]
        self.assertEqual(correct, result)

    def test_log_main_branch1(self):
        branch1 = self.encode_branch('branch1')
        result = [x.rev for x in self.repo.log(revrange=(self.main_branch, branch1))]
        correct = [14, 13, 11, 10, 9, 8, 4, 3]
        self.assertEqual(correct, result)


class SvnBranchTestStep13(SvnTest, common.BranchTestStep13):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['HEAD', self.encode_branch(self.main_branch)]
        self.assertEqual(sorted(correct), sorted(result))

    def test_log_main(self):
        result = self.repo.log(revrange=self.main_branch).rev
        correct = 15
        self.assertEqual(correct, result)

    def test_log_all(self):
        result = [x.rev for x in self.repo.log()]
        correct = list(range(18, -1, -1))
        self.assertEqual(correct, result)

    def test_log_None_main(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch))]
        correct = list(range(15, 0, -1))
        self.assertEqual(correct, result)

    def test_log_None_main_path_b(self):
        result = [x.rev for x in self.repo.log(revrange=(None, self.main_branch), path='/b')]
        correct = [15, 11, 4]
        self.assertEqual(correct, result)


class SvnCacheTest(SvnTest, common.CacheTest):
    def test_log_all(self):
        for i in range(2):
            result = self.repo.log()
            self.assertIsInstance(result, list)
            self.assertEqual(2, len(result))
            self.assertIsInstance(result[0], CommitLogEntry)
            self.assertEqual(self.rev1, result[0].rev)
            self.assertIsInstance(result[0].date, datetime.datetime)
        self.assertTrue(result[0]._cached)


class SvnUTF8EncodingTest(SvnTest, common.UTF8EncodingTest):
    pass

# Don't do these tests for now because many systems won't have the latin1
# locale and the tests will fail.    Also, Mercurial and Subversion will fail
# by default if you give them non-UTF-8 strings.
#
#class SvnLatin1EncodingTest(SvnTest, common.Latin1EncodingTest): pass


class SvnCopyTest(SvnTest, common.CopyTest):
    pass


### TEST CASE: SvnHeadRevTest ###

class SvnHeadRevTest(SvnTest):
    @classmethod
    def setUpWorkingCopy(cls, working_path):
        yield common.CreateStandardDirectoryStructure()
        cls.rev0 = cls.getAbsoluteRev()

        os.makedirs(os.path.join(working_path, 'a'))
        common.touch(os.path.join(working_path, 'a', 'b'), 'foo\n')
        yield common.Commit('create a/b')
        cls.rev1 = cls.getAbsoluteRev()

    def test_ls1(self):
        expected = [
            {'name': 'a', 'path': 'trunk/a', 'type': 'd'},
        ]
        result = self.repo.ls(self.rev1, '')
        self.assertEqual(common.normalize_ls(expected), common.normalize_ls(result))

    def test_ls2(self):
        expected = [
            {'name': 'a', 'path': 'trunk/a', 'type': 'd'},
        ]
        result = self.repo.ls(self.rev1, '/')
        self.assertEqual(common.normalize_ls(expected), common.normalize_ls(result))

    def test_ls3(self):
        expected = [
            {'name': 'b', 'path': 'trunk/a/b', 'type': 'f'},
        ]
        result = self.repo.ls(self.rev1, '/a')
        self.assertEqual(common.normalize_ls(expected), common.normalize_ls(result))

    def test_ls3(self):
        expected = [
            {'name': 'b', 'path': 'trunk/a/b', 'type': 'f'},
        ]
        result = self.repo.ls(self.rev1, 'a')
        self.assertEqual(common.normalize_ls(expected), common.normalize_ls(result))

    def test_ls4(self):
        expected = [
            {'name': 'b', 'path': 'trunk/a/b', 'type': 'f'},
        ]
        result = self.repo.ls(self.rev1, 'a/')
        self.assertEqual(common.normalize_ls(expected), common.normalize_ls(result))

    def test_diff1(self):
        diff = self.repo.diff(self.rev0, self.rev1, 'a/b')
        self.assertIsInstance(diff, common.string_types)
        self.assertTrue(len(diff) > 0)


if __name__ == "__main__":
    common.unittest.main()
