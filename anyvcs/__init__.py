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

__version__ = '1.3.1'


def create(path, vcs):
    """Create a new repository

    vcs is either 'git', 'hg', or 'svn'

    """
    from .common import UnknownVCSType
    if vcs == 'git':
        from .git import GitRepo
        cls = GitRepo
    elif vcs == 'hg':
        from .hg import HgRepo
        cls = HgRepo
    elif vcs == 'svn':
        from .svn import SvnRepo
        cls = SvnRepo
    else:
        raise UnknownVCSType(vcs)
    return cls.create(path)


def open(path, vcs=None):
    """Open an existing repository

    vcs can be specified to avoid auto-detection of repository type

    """
    import os
    from .common import UnknownVCSType
    assert os.path.isdir(path), path + ' is not a directory'
    if vcs == 'git':
        from .git import GitRepo
        cls = GitRepo
    elif vcs == 'hg':
        from .hg import HgRepo
        cls = HgRepo
    elif vcs == 'svn':
        from .svn import SvnRepo
        cls = SvnRepo
    elif os.path.isdir(os.path.join(path, '.git')):
        from .git import GitRepo
        cls = GitRepo
    elif os.path.isdir(os.path.join(path, '.hg')):
        from .hg import HgRepo
        cls = HgRepo
    elif (
        os.path.isfile(os.path.join(path, 'config')) and
        os.path.isdir(os.path.join(path, 'objects')) and
        os.path.isdir(os.path.join(path, 'refs')) and
        os.path.isdir(os.path.join(path, 'branches'))
    ):
        from .git import GitRepo
        cls = GitRepo
    elif (
        os.path.isfile(os.path.join(path, 'format')) and
        os.path.isdir(os.path.join(path, 'conf')) and
        os.path.isdir(os.path.join(path, 'db')) and
        os.path.isdir(os.path.join(path, 'locks'))
    ):
        from .svn import SvnRepo
        cls = SvnRepo
    else:
        raise UnknownVCSType(path)
    return cls(path)
