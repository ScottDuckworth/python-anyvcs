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

import os
import subprocess


class HgTest(common.VCSTest):
    vcs = 'hg'

    @classmethod
    def setUpRepos(cls):
        cls.repo = anyvcs.create(cls.main_path, 'hg')
        common.check_call(['hg', 'clone', cls.main_path, cls.working_path])
        with open(os.path.join(cls.working_path, '.hg', 'hgrc'), 'a') as hgrc:
            hgrc.write('[ui]\nusername = Test User <me@example.com>\n')
        cls.main_branch = 'default'
        cls.working_head = 'default'
        for action in cls.setUpWorkingCopy(cls.working_path):
            action.doHg(cls)

    @classmethod
    def getAbsoluteRev(cls):
        return cls.check_output(['hg', 'log', '-l1', '--template={node}']).decode()

    @classmethod
    def export(cls, rev, path):
        common.check_call(['hg', 'archive', '-r', str(rev), path], cwd=cls.main_path)
        trash = os.path.join(path, '.hg_archival.txt')
        if os.path.exists(trash):
            os.unlink(trash)


class HgEmptyTest(HgTest, common.EmptyTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = ['tip']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_bookmarks(self):
        result = self.repo.bookmarks()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = ['tip']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_log(self):
        result = self.repo.log()
        self.assertEqual(len(result), 0)

    def test_changed(self):
        result = self.repo.changed('null')
        correct = []
        self.assertEqual(correct, result)


class HgEmptyWithCommitsTest(HgTest, common.EmptyWithCommitsTest):
    pass


class HgMismatchedFileTypeTest(HgTest, common.MismatchedFileTypeTest):
    pass


class HgEmptyMainBranchTest(HgTest, common.EmptyMainBranchTest):
    pass


class HgBasicTest(HgTest, common.GitLikeBasicTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['default']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = ['tip']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_bookmarks(self):
        result = self.repo.bookmarks()
        correct = ['rev0']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = ['rev0', 'default', 'tip']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))


class HgUnrelatedBranchTest(HgTest, common.UnrelatedBranchTest):
    pass


class HgBranchTestStep3(HgTest, common.GitLikeBranchTestStep3):
    pass


class HgBranchTestStep7(HgTest, common.GitLikeBranchTestStep7):
    pass


class HgBranchTestStep9(HgTest, common.GitLikeBranchTestStep9):
    pass


class HgBranchTestStep11(HgTest, common.GitLikeBranchTestStep11):
    pass


class HgBranchTestStep13(HgTest, common.GitLikeBranchTestStep13):
    def test_log_all(self):
        result = [self.revrev[x.rev] for x in self.repo.log()]
        correct = [18, 17, 16, 15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
        self.assertEqual(correct, result)


class HgCacheTest(HgTest, common.CacheTest):
    def test_ls(self):
        correct = [
            {'path': 'a', 'name': 'a', 'type': 'f', 'commit': self.rev1}
        ]
        for i in range(2):
            result = self.repo.ls(self.main_branch, '/', report=['commit'])
            self.assertEqual(correct, result)
        self.assertTrue(result[0]._commit_cached)


class HgUTF8EncodingTest(HgTest, common.UTF8EncodingTest):
    pass


# Don't do these tests for now because many systems won't have the latin1
# locale and the tests will fail.    Also, Mercurial and Subversion will fail
# by default if you give them non-UTF-8 strings.
#
#class HgLatin1EncodingTest(HgTest, common.Latin1EncodingTest): pass


class HgCopyTest(HgTest, common.CopyTest):
    pass


if __name__ == "__main__":
    common.unittest.main()
