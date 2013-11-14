python-anyvcs
=============

A Python abstraction layer for multiple version control systems.

.. image:: https://travis-ci.org/ScottDuckworth/python-anyvcs.png?branch=master
   :target: https://travis-ci.org/ScottDuckworth/python-anyvcs
   :alt: Build Status

.. image:: https://badge.fury.io/py/anyvcs.png
   :target: http://badge.fury.io/py/anyvcs
   :alt: PyPI Package

python-anyvcs provides a Python interface to work with version control
repositories through a consistent interface regardless of the underlying
repository type.  It currently supports:

* Git repositories (either bare or non-bare)
* Mercurial repositories
* Subversion master repositories (those created with ``svnadmin create``)

The focus is on read-only operations, but a few write operations are supported
(like creating new repositories or loading a Subversion dumpfile).

If you are looking for an interface to work with working copies of version
control repositories, either contribute to this project or look elsewhere.

Supported Operations
--------------------

* ``ls()`` - list files
* ``cat()`` - read file contents
* ``readlink()`` - read symbolic link target
* ``branches()`` - list branches
* ``bookmarks()`` - list bookmarks (Mercurial only)
* ``tags()`` - list tags
* ``heads()`` - list all branches, bookmarks, tags, etc.
* ``empty()`` - determine if the repository contains any commits
* ``__len__()`` - count the number of commits in the repository
* ``__contains__()`` - determine if the repository contains the given revision
* ``log()`` - get commit logs
* ``changed()`` - list files that were changed in a given revision
* ``pdiff()`` - get diff that a given revision introduced
* ``diff()`` - get diff between any two revisions
* ``ancestor()`` - find most recent common ancestor of any two revisions
* ``blame()`` - blame (a.k.a. annotate) lines of a file
* ``canonical_rev()`` - get the canonical revision identifier
* ``private_path`` - a path in the repository where untracked data can be stored
* ``dump()`` - create a Subversion dumpfile (Subversion only)
* ``load()`` - load a Subversion dumpfile (Subversion only)

Operations that are not natively supported by the underlying version control
system are implemented in this library.

Example
-------

    >>> from pprint import pprint
    >>> import anyvcs
    >>> repo = anyvcs.open('/path/to/repo')
    >>> repo.branches()
    ['1.0_develop', '1.0_master', 'develop', 'master']
    >>>
    >>> log = repo.log(limit=3)
    >>> pprint([commit.message for commit in log])
    ["Merge branch 'release/1.2.0' into develop\n",
     "Merge branch 'release/1.2.0'\n",
     'add README symlink to keep python happy\n',
     'add copyright information\n']
    >>>
    >>> ls = repo.ls('master', '/')
    >>> pprint(ls)
    [{'name': '.gitignore', 'path': '.gitignore', 'type': 'f'},
     {'name': 'AUTHORS', 'path': 'AUTHORS', 'type': 'f'},
     {'name': 'COPYING', 'path': 'COPYING', 'type': 'f'},
     {'name': 'COPYING.LESSER', 'path': 'COPYING.LESSER', 'type': 'f'},
     {'name': 'LICENSE', 'path': 'LICENSE', 'type': 'f'},
     {'name': 'MANIFEST.in', 'path': 'MANIFEST.in', 'type': 'f'},
     {'name': 'README', 'path': 'README', 'type': 'l'},
     {'name': 'README.md', 'path': 'README.md', 'type': 'f'},
     {'name': 'RELEASE-NOTES.txt', 'path': 'RELEASE-NOTES.txt', 'type': 'f'},
     {'name': 'anyvcs', 'path': 'anyvcs', 'type': 'd'},
     {'name': 'setup.py', 'path': 'setup.py', 'type': 'f'},
     {'name': 'tests.py', 'path': 'tests.py', 'type': 'f'}]

Compatibility
-------------

python-anyvcs should work with the following software versions:

* Python: 2.6 or later (including 3.0 or later)
* Git: 1.7.0 or later
* Mercurial: 1.6.1 or later
* Subversion: 1.5 or later
