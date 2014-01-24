.. python-anyvcs documentation master file, created by
   sphinx-quickstart on Thu Nov 21 12:32:44 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

python-anyvcs
=============

python-anyvcs is an abstraction layer for the homogenous, local handling of:

* Bare and non-bare Git repositories
* Mercurial repositories
* Subversion repositories (what ``svnadmin create`` makes)

Getting Started
---------------

Here's a simple example for an existing repository:

    >>> import anyvcs
    >>> repo = anyvcs.open('/path/to/repo')

``repo`` is an instance of :class:`anyvcs.common.VCSRepo` with a variety of
operations available for it.

Contents
--------

.. toctree::
   :maxdepth: 2

   anyvcs

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

