"""Durable jobs: submission, durable execution on DBOS, status and the worker.

Internal: the public operations are :meth:`brevia.Brevia.submit` and
:class:`brevia.RunHandle`. DBOS is an implementation detail and never appears in the
public API (specification §7.5, §11.4).
"""
