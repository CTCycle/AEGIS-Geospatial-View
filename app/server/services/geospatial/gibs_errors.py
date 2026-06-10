from __future__ import annotations


###############################################################################
class GIBSServiceError(Exception):
    """Base exception for GIBS service failures."""

###############################################################################
class GIBSValidationError(GIBSServiceError):
    """Raised when user input cannot produce a valid WMS request."""

###############################################################################
class GIBSRequestError(GIBSServiceError):
    """Raised when NASA endpoints cannot fulfill the request."""

###############################################################################
class GIBSPayloadIntegrityError(GIBSRequestError):
    """Raised when NASA returns incomplete imagery payloads."""