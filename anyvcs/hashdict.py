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

import collections
import errno
import fcntl
import os

class HashDict(collections.MutableMapping):
  """A dictionary-like object for hex keys and string values that is stored
  on-disk and is multi-process safe.
  """

  def __init__(self, path, mode=0666):
    self.path = path
    self.mode = mode
    self.dirmode = mode | (mode >> 1) & 0111 | (mode >> 2) & 0111
    try:
      os.mkdir(path, self.dirmode)
    except OSError as e:
      if e.errno != errno.EEXIST:
        raise

  def __contains__(self, key):
    int(key, 16)
    p = os.path.join(self.path, key[:2], key[2:])
    return os.path.isfile(p)

  def __getitem__(self, key):
    int(key, 16)
    p = os.path.join(self.path, key[:2], key[2:])
    try:
      with open(p, 'r') as f:
        fcntl.lockf(f, fcntl.LOCK_SH)
        return f.read()
    except IOError as e:
      if e.errno == errno.ENOENT:
        raise KeyError(key)
      raise

  def __setitem__(self, key, value):
    assert isinstance(value, str)
    int(key, 16)
    d = os.path.join(self.path, key[:2])
    p = os.path.join(d, key[2:])
    try:
      os.mkdir(d, self.dirmode)
    except OSError as e:
      if e.errno != errno.EEXIST:
        raise
    fd = None
    try:
      fd = os.open(p, os.O_WRONLY | os.O_CREAT, self.mode)
      fcntl.lockf(fd, fcntl.LOCK_EX)
      os.ftruncate(fd, 0)
      with os.fdopen(fd, 'w') as f:
        fd = None
        f.write(value)
    finally:
      if fd is not None:
        os.close(fd)

  def __delitem__(self, key):
    int(key, 16)
    d = os.path.join(self.path, key[:2])
    p = os.path.join(d, key[2:])
    try:
      os.unlink(p)
    except OSError as e:
      if e.errno == ENOENT:
        raise KeyError(key)
      raise

  def __iter__(self):
    for d in os.listdir(self.path):
      try:
        int(d, 16)
      except ValueError:
        continue
      p = os.path.join(self.path, d)
      for k in os.listdir(p):
        try:
          int(k, 16)
        except ValueError:
          continue
        if os.path.isfile(os.path.join(p, k)):
          yield d + k

  def __len__(self):
    return len(list(self.__iter__()))
