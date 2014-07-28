# Copyright (c) 2013, Clemson University
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
# * Neither the name of the {organization} nor the names of its
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


class GitTest(common.VCSTest):
    vcs = 'git'

    @classmethod
    def setUpRepos(cls):
        cls.repo = anyvcs.create(cls.main_path, 'git')
        common.check_call(['git', 'clone', cls.main_path, cls.working_path])
        cls.check_call(['git', 'config', 'user.email', 'me@example.com'])
        cls.check_call(['git', 'config', 'user.name', 'Test User'])
        cls.main_branch = 'master'
        cls.working_head = 'master'
        for action in cls.setUpWorkingCopy(cls.working_path):
            action.doGit(cls)

    @classmethod
    def getAbsoluteRev(cls):
        try:
            return cls.check_output(['git', 'log', '-1', '--pretty=format:%H']).decode()
        except subprocess.CalledProcessError:
            return None

    @classmethod
    def export(cls, rev, path):
        os.mkdir(path)
        cmd1 = ['git', 'archive', rev]
        data = common.check_output(cmd1, cwd=cls.main_path)
        cmd2 = ['tar', '-x', '-C', path]
        p = subprocess.Popen(cmd2, stdin=subprocess.PIPE)
        p.communicate(data)
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd2)


class GitEmptyTest(GitTest, common.EmptyTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_log(self):
        result = self.repo.log()
        self.assertEqual(len(result), 0)


class GitEmptyWithCommitsTest(GitTest, common.EmptyWithCommitsTest):
    pass


class GitEmptyMainBranchTest(GitTest, common.EmptyMainBranchTest):
    pass


class GitBasicTest(GitTest, common.GitLikeBasicTest):
    def test_branches(self):
        result = self.repo.branches()
        correct = ['master']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_tags(self):
        result = self.repo.tags()
        correct = []
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))

    def test_heads(self):
        result = self.repo.heads()
        correct = ['master']
        self.assertEqual(common.normalize_heads(correct), common.normalize_heads(result))


class GitUnrelatedBranchTest(GitTest, common.UnrelatedBranchTest):
    pass


class GitBranchTestStep3(GitTest, common.GitLikeBranchTestStep3):
    pass


class GitBranchTestStep7(GitTest, common.GitLikeBranchTestStep7):
    pass


class GitBranchTestStep9(GitTest, common.GitLikeBranchTestStep9):
    pass


class GitBranchTestStep11(GitTest, common.GitLikeBranchTestStep11):
    pass


class GitBranchTestStep13(GitTest, common.GitLikeBranchTestStep13):
    def test_log_all(self):
        result = [self.revrev[x.rev] for x in self.repo.log()]
        correct = [15, 14, 13, 12, 11, 10, 8, 7, 5, 4, 2]
        self.assertEqual(correct, result)


class GitCacheTest(GitTest, common.CacheTest):
    pass


class GitUTF8EncodingTest(GitTest, common.UTF8EncodingTest):
    pass


# Don't do these tests for now because many systems won't have the latin1
# locale and the tests will fail.    Also, Mercurial and Subversion will fail
# by default if you give them non-UTF-8 strings.
#
#class GitLatin1EncodingTest(GitTest, common.Latin1EncodingTest): pass


class GitCopyTest(GitTest, common.CopyTest):
    pass
