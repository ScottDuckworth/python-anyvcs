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

import datetime
import json
import os
import re
import subprocess
from abc import ABCMeta, abstractmethod, abstractproperty
from functools import wraps
from .hashdict import HashDict

multislash_rx = re.compile(r'//+')
isodate_rx = re.compile(r'(?P<year>\d{4})-?(?P<month>\d{2})-?(?P<day>\d{2})(?:\s*(?:T\s*)?(?P<hour>\d{2})(?::?(?P<minute>\d{2})(?::?(?P<second>\d{2}))?)?(?:[,.](?P<fraction>\d+))?(?:\s*(?P<tz>(?:Z|[+-](?P<tzhh>\d{2})(?::?(?P<tzmm>\d{2}))?)))?)')
tz_rx = re.compile(r'^(?P<tz>(?:Z|[+-](?P<tzhh>\d{2})(?::?(?P<tzmm>\d{2}))?))$')


def parse_isodate(datestr):
    """Parse a string that loosely fits ISO 8601 formatted date-time string
    """
    m = isodate_rx.search(datestr)
    assert m, 'unrecognized date format: ' + datestr
    year, month, day = m.group('year', 'month', 'day')
    hour, minute, second, fraction = m.group('hour', 'minute', 'second', 'fraction')
    tz, tzhh, tzmm = m.group('tz', 'tzhh', 'tzmm')
    dt = datetime.datetime(int(year), int(month), int(day), int(hour))
    if fraction is None:
        fraction = 0
    else:
        fraction = float('0.' + fraction)
    if minute is None:
        dt = dt.replace(minute=int(60 * fraction))
    else:
        dt = dt.replace(minute=int(minute))
        if second is None:
            dt = dt.replace(second=int(60 * fraction))
        else:
            dt = dt.replace(second=int(second), microsecond=int(1000000 * fraction))
    if tz is not None:
        if tz[0] == 'Z':
            offset = 0
        else:
            offset = datetime.timedelta(minutes=int(tzmm or 0), hours=int(tzhh))
            if tz[0] == '-':
                offset = -offset
        dt = dt.replace(tzinfo=UTCOffset(offset))
    return dt


def command(cmd, input=None, **kwargs):
    try:
        output = subprocess.check_output(cmd, **kwargs)
        return output
    except AttributeError:  # subprocess.check_output added in python 2.7
        kwargs.setdefault('stdout', subprocess.PIPE)
        p = subprocess.Popen(cmd, **kwargs)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd)
        return stdout


class ABCMetaDocStringInheritor(ABCMeta):
    '''A variation on
    http://groups.google.com/group/comp.lang.python/msg/26f7b4fcb4d66c95
    by Paul McGuire
    '''
    def __new__(meta, name, bases, clsdict):
        if not('__doc__' in clsdict and clsdict['__doc__']):
            for mro_cls in (mro_cls for base in bases for mro_cls in base.mro()):
                doc = mro_cls.__doc__
                if doc:
                    clsdict['__doc__'] = doc
                    break
        for attr, attribute in clsdict.items():
            if not attribute.__doc__:
                for mro_cls in (
                    mro_cls for base in bases for mro_cls in base.mro()
                    if hasattr(mro_cls, attr)
                ):
                    doc = getattr(getattr(mro_cls, attr), '__doc__')
                    if doc:
                        attribute.__doc__ = doc
                        break
        return ABCMeta.__new__(meta, name, bases, clsdict)


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
        if name.startswith('_'):
            dict.__setattr__(self, name, value)
        else:
            self.__setitem__(name, value)

    def __delattr__(self, name):
        self.__delitem__(name)


class CommitLogEntry(object):
    """Represents a single entry in the commit log

    :ivar rev: Revision name
    :ivar parents: Parents of the revision
    :ivar datetime date: Timestamp of the revision
    :ivar str author: Author of the revision
    :ivar str message: Message from committer
    """
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
        """First line of the commit message."""
        return self.message.split('\n', 1)[0]

    def to_json(self):
        return json.dumps({
            'v': 1,
            'r': self.rev,
            'p': self.parents,
            'd': self.date.isoformat(),
            'a': self.author,
            'm': self.message,
        })

    @classmethod
    def from_json(cls, s):
        o = json.loads(s)
        if o.get('v') != 1:
            return None
        return cls(
            rev=o['r'],
            parents=o['p'],
            date=parse_isodate(o['d']),
            author=o['a'],
            message=o['m'],
        )


class CommitLogCache(HashDict):
    def __getitem__(self, key):
        value = HashDict.__getitem__(self, key)
        value = CommitLogEntry.from_json(value.decode())
        if value:
            return value
        raise KeyError(key)

    def __setitem__(self, key, value):
        value = value.to_json().encode()
        HashDict.__setitem__(self, key, value)


class FileChangeInfo(object):
    """Represents a change to a single path.

    :ivar str path: The path that was changed.
    :ivar str status: VCS-specific code for the change type.
    :ivar copy: The source path copied from, if any.
    """
    def __init__(self, path, status, copy=None):
        self.path = path
        self.status = status
        self.copy = copy


class BlameInfo(object):
    """Represents an annotated line in a file for a blame view.

    :ivar rev: Revision at which the line was last changed
    :ivar str author: Author of the change
    :ivar datetime date: Timestamp of the change
    :ivar str line: Line data from the file.
    """
    def __init__(self, rev, author, date, line):
        self.rev = rev
        self.author = author
        self.date = date
        self.line = line


class UTCOffset(datetime.tzinfo):
    ZERO = datetime.timedelta()

    def __init__(self, offset, name=None):
        if isinstance(offset, datetime.timedelta):
            self.offset = offset
        elif isinstance(offset, str):
            m = tz_rx.match(offset)
            assert m
            tz, tzhh, tzmm = m.group('tz', 'tzhh', 'tzmm')
            offset = datetime.timedelta(minutes=int(tzmm or 0), hours=int(tzhh))
            if tz[0] == '-':
                offset = -offset
            self.offset = offset
        else:
            self.offset = datetime.timedelta(minutes=offset)
        if name is not None:
            self.name = name
        elif self.offset < type(self).ZERO:
            self.name = '-%02d%02d' % divmod((-self.offset).seconds / 60, 60)
        else:
            self.name = '+%02d%02d' % divmod(self.offset.seconds / 60, 60)

    def utcoffset(self, dt):
        return self.offset

    def dst(self, dt):
        return type(self).ZERO

    def tzname(self, dt):
        return self.name


class VCSRepo(object):
    __metaclass__ = ABCMetaDocStringInheritor

    def __init__(self, path, encoding='utf-8'):
        """Open an existing repository"""
        self.path = path
        self.encoding = encoding

    @abstractproperty
    def private_path(self):
        """Get the path to a directory which can be used to store arbitrary data

        This directory should not conflict with any of the repository internals.
        The directory should be created if it does not already exist.

        """
        raise NotImplementedError

    @property
    def _commit_cache(self):
        try:
            return self._commit_cache_v
        except AttributeError:
            commit_cache_path = os.path.join(self.private_path, 'commit-cache')
            self._commit_cache_v = CommitLogCache(commit_cache_path)
            return self._commit_cache_v

    def _command(self, cmd, input=None, **kwargs):
        kwargs.setdefault('cwd', self.path)
        return command(cmd, **kwargs)

    @classmethod
    def cleanPath(cls, path):
        path = path.lstrip('/')
        path = multislash_rx.sub('/', path)
        return path

    @abstractmethod
    def canonical_rev(self, rev):
        """ Get the canonical revision identifier

        :param rev: The revision to canonicalize.
        :returns: The canonicalized revision

        The canonical revision is the revision which is natively supported by
        the underlying VCS type. In some cases, anyvcs may annotate a revision
        identifier to also encode branch information which is not safe to use
        directly with the VCS itself (e.g. as created by :meth:`compose_rev`).
        This method is a means of converting back to canonical form.

        """
        raise NotImplementedError

    @abstractmethod
    def compose_rev(self, branch, rev):
        """ Compose a revision identifier which encodes branch and revision.

        :param str branch: A branch name
        :param rev: A revision (can be canonical or as constructed by
                    :meth:`compose_rev()` or :meth:`tip()`)

        The revision identifier encodes branch and revision information
        according to the particular VCS type. This is a means to unify the
        various branching models under a common interface.

        """
        raise NotImplementedError

    @abstractmethod
    def ls(
        self, rev, path, recursive=False, recursive_dirs=False,
        directory=False, report=()
    ):
        """List directory or file

        :param rev: The revision to use.
        :param path: The path to list. May start with a '/' or not. Directories
                     may end with a '/' or not.
        :param recursive: Recursively list files in subdirectories.
        :param recursive_dirs: Used when recursive=True, also list directories.
        :param directory: If path is a directory, list path itself instead of
                          its contents.
        :param report: A list or tuple of extra attributes to return that may
                       require extra processing. Recognized values are 'size',
                       'target', 'executable', and 'commit'.

        Returns a list of dictionaries with the following keys:

        **type**
            The type of the file: 'f' for file, 'd' for directory, 'l' for
            symlink.
        **name**
            The name of the file. Not present if directory=True.
        **size**
            The size of the file. Only present for files when 'size' is in
            report.
        **target**
            The target of the symlink. Only present for symlinks when
            'target' is in report.
        **executable**
            True if the file is executable, False otherwise.    Only present
            for files when 'executable' is in report.

        Raises PathDoesNotExist if the path does not exist.

        """
        raise NotImplementedError

    @abstractmethod
    def cat(self, rev, path):
        """Get file contents

        :param rev: The revision to use.
        :param str path: The path to the file. Must be a file.
        :returns: The contents of the file.
        :rtype: str or bytes
        :raises PathDoesNotExist: If the path does not exist.
        :raises BadFileType: If the path is not a file.

        """
        raise NotImplementedError

    @abstractmethod
    def readlink(self, rev, path):
        """Get symbolic link target

        :param rev: The revision to use.
        :param str path: The path to the file. Must be a symbolic link.
        :returns str: The target of the symbolic link.
        :raises PathDoesNotExist: if the path does not exist.
        :raises BadFileType: if the path is not a symbolic link.

        """
        raise NotImplementedError

    @abstractmethod
    def branches(self):
        """Get list of branches

        :returns: The branches in the repository
        :rtype: list of str

        """
        raise NotImplementedError

    @abstractmethod
    def tags(self):
        """Get list of tags

        :returns: The tags in the repository
        :rtype: list of str

        """
        raise NotImplementedError

    @abstractmethod
    def heads(self):
        """Get list of heads

        :returns: The heads in the repository
        :rtype: list of str

        """
        raise NotImplementedError

    @abstractmethod
    def empty(self):
        """Test if the repository contains any commits

        :returns bool: True if the repository contains no commits.

        Commits that exist by default (e.g. a zero commit) are not counted.

        """
        return NotImplementedError

    @abstractmethod
    def __contains__(self, rev):
        """Test if the repository contains the specified revision
        """
        return NotImplementedError

    @abstractmethod
    def __len__(self):
        """Returns the number of commits in the repository

        Commits that exist by default (e.g. a zero commit) are not counted.
        """
        return NotImplementedError

    @abstractmethod
    def log(
        self, revrange=None, limit=None, firstparent=False, merges=None,
        path=None, follow=False
    ):
        """Get commit logs

        :param revrange: Either a single revision or a range of revisions as a
                         2-element list or tuple.
        :param int limit: Limit the number of log entries.
        :param bool firstparent: Only follow the first parent of merges.
        :param bool merges: True means only merges, False means no merges,
                            None means both merges and non-merges.
        :param str path: Only match commits containing changes on this path.
        :param bool follow: Follow file history across renames.
        :returns: log information
        :rtype: :class:`CommitLogEntry` or list of :class:`CommitLogEntry`

        If revrange is None, return a list of all log entries in reverse
        chronological order.

        If revrange is a single revision, return a single log entry.

        If revrange is a 2 element list [A,B] or tuple (A,B), return a list of log
        entries starting at B and following that branch back to A or one of its
        ancestors (not inclusive. If A is None, follow branch B back to the
        beginning of history. If B is None, list all descendants in reverse
        chronological order.

        """
        raise NotImplementedError

    @abstractmethod
    def changed(self, rev):
        """Files that changed from the rev's parent(s)

        :param rev: The revision to get the files that changed.
        :type rev: list of :class:`FileChangeInfo`.

        """
        raise NotImplementedError

    @abstractmethod
    def pdiff(self, rev):
        """Diff from the rev's parent(s)

        :param rev: The rev to compute the diff from its parent.
        :returns str: The diff.

        The returned string is a unified diff that the rev introduces with a
        prefix of one (suitable for input to patch -p1).

        """
        raise NotImplementedError

    @abstractmethod
    def diff(self, rev_a, rev_b, path=None):
        """Diff of two revisions

        :param rev_a: The start revision.
        :param rev_b: The end revision.
        :param path: If not None, return diff for only that file.
        :type path: None or str
        :returns str: The diff.

        The returned string contains the unified diff from rev_a to rev_b with
        a prefix of one (suitable for input to patch -p1).
        """
        raise NotImplementedError

    @abstractmethod
    def ancestor(self, rev1, rev2):
        """Find most recent common ancestor of two revisions

        :param rev1: First revision.
        :param rev2: Second revision.
        :returns: The common ancestor revision between the two.
        """
        raise NotImplementedError

    @abstractmethod
    def blame(self, rev, path):
        """Blame (a.k.a. annotate, praise) a file

        :param rev: The revision to blame.
        :param str path: The path to blame.
        :returns: list of annotated lines of the given path
        :rtype: list of :class:`BlameInfo` objects
        :raises PathDoesNotExist: if the path does not exist.
        :raises BadFileType: if the path is not a file.

        """
        raise NotImplementedError

    @abstractmethod
    def tip(self, head):
        """Find the tip of a named head

        :param str head: name of head to look up
        :returns: revision identifier of head

        The returned identifier should be a valid input for :meth:`VCSRepo.ls`.
        and respect the branch name in the returned identifier if applicable.

        """
        raise NotImplementedError

# vi:set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
