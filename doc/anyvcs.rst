The primary API
================

Opening and Creating
--------------------

In addition to instantiating subclasses of :class:`anyvcs.common.VCSRepo`
directly, you can also these utility functions which will infer the type based
on the given parameters.

.. module:: anyvcs

.. autofunction:: open

.. autofunction:: probe

.. autofunction:: create

.. module:: anyvcs.common

:class:`VCSRepo`
----------------

.. autoclass:: VCSRepo
   :members:

:class:`BlameInfo`
------------------

.. autoclass:: BlameInfo
   :members:

:class:`CommitLogEntry`
-----------------------

.. autoclass:: CommitLogEntry
   :members:

:class:`FileChangeInfo`
-----------------------

.. autoclass:: FileChangeInfo
   :members:
