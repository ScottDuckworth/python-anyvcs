# Copyright 2013 Scott Duckworth
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

import os
from common import UnknownVCSType, PathDoesNotExist, BadFileType

def create(path, vcs):
  if vcs == 'git':
    from git import GitRepo
    cls = GitRepo
  elif vcs == 'hg':
    from hg import HgRepo
    cls = HgRepo
  elif vcs == 'svn':
    from svn import SvnRepo
    cls = SvnRepo
  else:
    raise UnknownVCSType(vcs)
  return cls.create(path)

def open(path, vcs=None):
  assert os.path.isdir(path), path + ' is not a directory'
  if vcs == 'git':
    from git import GitRepo
    cls = GitRepo
  elif vcs == 'hg':
    from hg import HgRepo
    cls = HgRepo
  elif vcs == 'svn':
    from svn import SvnRepo
    cls = SvnRepo
  elif os.path.isdir(os.path.join(path, '.git')):
    from git import GitRepo
    cls = GitRepo
  elif os.path.isdir(os.path.join(path, '.hg')):
    from hg import HgRepo
    cls = HgRepo
  elif (os.path.isfile(os.path.join(path, 'config')) and
        os.path.isdir(os.path.join(path, 'objects')) and
        os.path.isdir(os.path.join(path, 'refs')) and
        os.path.isdir(os.path.join(path, 'branches'))):
    from git import GitRepo
    cls = GitRepo
  elif (os.path.isfile(os.path.join(path, 'format')) and
        os.path.isdir(os.path.join(path, 'conf')) and
        os.path.isdir(os.path.join(path, 'db')) and
        os.path.isdir(os.path.join(path, 'locks'))):
    from svn import SvnRepo
    cls = SvnRepo
  else:
    raise UnknownVCSType(path)
  return cls(path)
