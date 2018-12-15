from __future__ import annotations


class PyNixReqError(Exception):
	pass


class PyPINotAvailableError(PyNixReqError):
	pass


class NoSolutionError(PyNixReqError):
	pass
