from __future__ import annotations

###############################################################################
class RunServiceError(Exception):
    pass

###############################################################################
class RunNotFoundError(RunServiceError):
    pass

###############################################################################
class RunConflictError(RunServiceError):
    pass

###############################################################################
class RunAccessError(RunServiceError):
    pass
