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
