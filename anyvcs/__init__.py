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

from .version import __version__


def clone(srcpath, destpath, vcs=None):
    """Clone an existing repository.

    :param str srcpath: Path to an existing repository
    :param str destpath: Desired path of new repository
    :param str vcs: Either ``git``, ``hg``, or ``svn``
    :returns VCSRepo: The newly cloned repository

    If ``vcs`` is not given, then the repository type is discovered from
    ``srcpath`` via :func:`probe`.

    """
    vcs = vcs or probe(srcpath)
    cls = _get_repo_class(vcs)
    return cls.clone(srcpath, destpath)


def create(path, vcs):
    """Create a new repository

    :param str path: The path where to create the repository.
    :param str vcs: Either ``git``, ``hg``, or ``svn``

    """
    cls = _get_repo_class(vcs)
    return cls.create(path)


def probe(path):
    """Probe a repository for its type.

    :param str path: The path of the repository
    :raises UnknownVCSType: if the repository type couldn't be inferred
    :returns str: either ``git``, ``hg``, or ``svn``

    This function employs some heuristics to guess the type of the repository.

    """
    import os
    from .common import UnknownVCSType
    if os.path.isdir(os.path.join(path, '.git')):
        return 'git'
    elif os.path.isdir(os.path.join(path, '.hg')):
        return 'hg'
    elif (
        os.path.isfile(os.path.join(path, 'config')) and
        os.path.isdir(os.path.join(path, 'objects')) and
        os.path.isdir(os.path.join(path, 'refs')) and
        os.path.isdir(os.path.join(path, 'branches'))
    ):
        return 'git'
    elif (
        os.path.isfile(os.path.join(path, 'format')) and
        os.path.isdir(os.path.join(path, 'conf')) and
        os.path.isdir(os.path.join(path, 'db')) and
        os.path.isdir(os.path.join(path, 'locks'))
    ):
        return 'svn'
    else:
        raise UnknownVCSType(path)


def open(path, vcs=None):
    """Open an existing repository

    :param str path: The path of the repository
    :param vcs: If specified, assume the given repository type to avoid
                auto-detection. Either ``git``, ``hg``, or ``svn``.
    :raises UnknownVCSType: if the repository type couldn't be inferred

    If ``vcs`` is not specified, it is inferred via :func:`probe`.

    """
    import os
    assert os.path.isdir(path), path + ' is not a directory'
    vcs = vcs or probe(path)
    cls = _get_repo_class(vcs)
    return cls(path)


def _get_repo_class(vcs):
    from .common import UnknownVCSType
    if vcs == 'git':
        from .git import GitRepo
        return GitRepo
    elif vcs == 'hg':
        from .hg import HgRepo
        return HgRepo
    elif vcs == 'svn':
        from .svn import SvnRepo
        return SvnRepo
    else:
        raise UnknownVCSType(vcs)

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
