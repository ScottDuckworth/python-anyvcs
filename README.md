python-anyvcs
=============

A Python abstraction layer for multiple version control systems.

Example usage:

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
