import re
import subprocess
from abc import ABCMeta, abstractmethod

multislash_rx = re.compile(r'//+')

class UnknownVCSType(Exception):
  pass

class RevisionPathException(Exception):
  def __init__(self, rev, path):
    super(RevisionPathException, self).__init__(rev, path)

class PathDoesNotExist(RevisionPathException):
  pass

class BadFileType(RevisionPathException):
  pass

class attrdict(dict):
  def __getattr__(self, name):
    return self.__getitem__(name)
  def __setattr__(self, name, value):
    self.__setitem__(name, value)
  def __delattr__(self, name):
    self.__delitem__(name)

class VCSRepo(object):
  __metaclass__ = ABCMeta

  def __init__(self, path):
    self.path = path

  def _command(self, cmd, input=None, **kwargs):
    kwargs.setdefault('cwd', self.path)
    return subprocess.check_output(cmd, **kwargs)

  @classmethod
  def cleanRev(cls, rev):
    return str(rev)

  @classmethod
  def cleanPath(cls, path):
    path = path.lstrip('/')
    path = multislash_rx.sub('/', path)
    return path

  @abstractmethod
  def ls(self, rev, path, recursive=False, recursive_dirs=False,
         directory=False, report=()):
    """List directory or file

    Arguments:
    rev             The revision to use.
    path            The path to list. May start with a '/' or not. Directories
                    may end with a '/' or not.
    recursive       Recursively list files in subdirectories.
    recursive_dirs  Used when recursive=True, also list directories.
    directory       If path is a directory, list path itself instead of its
                    contents.
    report          A list or tuple of extra attributes to return that may
                    require extra processing. Recognized values are 'size',
                    'target', and 'executable'.

    Returns a list of dictionaries with the following keys:
    type        The type of the file: 'f' for file, 'd' for directory, 'l' for
                symlink.
    name        The name of the file. Not present if directory=True.
    size        The size of the file. Only present for files when 'size' is in
                report.
    target      The target of the symlink. Only present for symlinks when
                'target' is in report.
    executable  True if the file is executable, False otherwise.  Only present
                for files when 'executable' is in report.

    Raises PathDoesNotExist if the path does not exist.

    """
    raise NotImplementedError

  @abstractmethod
  def cat(self, rev, path):
    """Get file contents

    Arguments:
    rev             The revision to use.
    path            The path to the file. Must be a file.

    Returns the file contents as a string.

    Raises PathDoesNotExist if the path does not exist.
    Raises BadFileType if the path is not a file.

    """
    raise NotImplementedError

  @abstractmethod
  def readlink(self, rev, path):
    """Get symbolic link target

    Arguments:
    rev             The revision to use.
    path            The path to the file. Must be a symbolic link.

    Returns the target of the symbolic link as a string.

    Raises PathDoesNotExist if the path does not exist.
    Raises BadFileType if the path is not a symbolic link.

    """
    raise NotImplementedError

  @abstractmethod
  def branches(self):
    """Get list of branches
    """
    raise NotImplementedError

  @abstractmethod
  def tags(self):
    """Get list of tags
    """
    raise NotImplementedError

  @abstractmethod
  def heads(self):
    """Get list of heads
    """
    raise NotImplementedError
