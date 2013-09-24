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

import datetime
import re
import subprocess
from abc import ABCMeta, abstractmethod

multislash_rx = re.compile(r'//+')
isodate_rx = re.compile(r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{1,2})\s+(?P<tz>[+-]?\d{4})')

def parse_isodate(datestr):
  m = isodate_rx.search(datestr)
  assert m, 'unrecognized date format: ' + datestr
  date = datetime.datetime(*[int(x) for x in m.group('year', 'month', 'day', 'hour', 'minute', 'second')])
  tz = m.group('tz')
  offset = datetime.timedelta(minutes=int(tz[-2:]), hours=int(tz[-4:-2]))
  if tz[0] == '-':
    offset = -offset
  return date.replace(tzinfo=UTCOffset(offset))

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

class CommitLogEntry(object):
  def __init__(self, rev, parents, date, author, message):
    self.rev = rev
    self.parents = parents
    self.date = date
    self.author = author
    self.message = message

  def __str__(self):
    return str(self.rev)

  def __repr__(self):
    return str('<%s.%s %s>' % (type(self).__module__, type(self).__name__, self.rev))

  @property
  def subject(self):
    return self.message.split('\n', 1)[0]

class UTCOffset(datetime.tzinfo):
  ZERO = datetime.timedelta()

  def __init__(self, offset, name=None):
    if isinstance(offset, datetime.timedelta):
      self.offset = offset
    else:
      self.offset = datetime.timedelta(minutes=offset)
    if name is not None:
      self.name = name
    elif self.offset < type(self).ZERO:
      self.name = '-%02d%02d' % divmod((-self.offset).seconds/60, 60)
    else:
      self.name = '+%02d%02d' % divmod(self.offset.seconds/60, 60)

  def utcoffset(self, dt):
    return self.offset

  def dst(self, dt):
    return type(self).ZERO

  def tzname(self, dt):
    return self.name

class VCSRepo(object):
  __metaclass__ = ABCMeta

  def __init__(self, path):
    self.path = path

  def _command(self, cmd, input=None, **kwargs):
    kwargs.setdefault('cwd', self.path)
    return subprocess.check_output(cmd, **kwargs)

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

  @abstractmethod
  def empty(self):
    """Test if the repository contains any commits
    """
    return NotImplementedError

  @abstractmethod
  def log(self, revrange=None, limit=None, firstparent=False, merges=None,
          path=None, follow=False):
    """Get commit logs

    Arguments:
    revrange     Either a single revision or a range of revisions as a 2-tuple.
    limit        Limit the number of log entries.
    firstparent  Only follow the first parent of merges.
    merges       True means only merges, False means no merges, None means
                 both merges and non-merges.
    path         Only match commits containing changes on this path.
    follow       Follow file history across renames.

    If revrange is None, return a list of all log entries in reverse
    chronological order.

    If revrange is a single revision, return a single log entry.

    If revrange is a 2-tuple (A,B), return a list of log entries starting at
    B and following that branch back to A or one of its ancestors (not
    inclusive. If A is None, follow branch B back to the beginning of history.
    If B is None, list all descendants in reverse chronological order.

    """
    raise NotImplementedError

  @abstractmethod
  def diff(self, rev_a, rev_b, path=None):
    """Diff of two revisions

    Returns a string containing the unified diff from rev_a to rev_b with a
    prefix of one (suitable for input to patch -p1). If path is not None, only
    return the diff for that file.
    """
    raise NotImplementedError

  @abstractmethod
  def ancestor(self, rev1, rev2):
    """Find most recent common ancestor of two revisions
    """
    raise NotImplementedError
