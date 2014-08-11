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

import collections
import errno
import fcntl
import os


class HashDict(collections.MutableMapping):
    """A dictionary-like object for hex keys and string values that is stored
    on-disk and is multi-process safe.
    """

    def __init__(self, path, mode=0o666):
        self.path = path
        self.mode = mode
        self.dirmode = mode | (mode >> 1) & 0o111 | (mode >> 2) & 0o111
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
            with open(p, 'rb') as f:
                fcntl.lockf(f, fcntl.LOCK_SH)
                return f.read()
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise KeyError(key)
            raise

    def __setitem__(self, key, value):
        int(key, 16)
        d = os.path.join(self.path, key[:2])
        p = os.path.join(d, key[2:])
        try:
            os.mkdir(d, self.dirmode)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        with open(p, 'ab+', self.mode) as f:
            fcntl.lockf(f, fcntl.LOCK_EX)
            os.ftruncate(f.fileno(), 0)
            f.write(value)

    def __delitem__(self, key):
        int(key, 16)
        d = os.path.join(self.path, key[:2])
        p = os.path.join(d, key[2:])
        try:
            os.unlink(p)
        except OSError as e:
            if e.errno == errno.ENOENT:
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

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
