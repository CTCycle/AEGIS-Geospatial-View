from __future__ import annotations


class MapSearchExecutionError(Exception):
    """Base exception for map search execution failures."""


class MapSearchJobInitializationError(MapSearchExecutionError):
    """Raised when a started map search job cannot be resolved."""


class MapSearchJobNotFoundError(MapSearchExecutionError):
    """Raised when a requested map search job does not exist."""


class MapSearchTileProxyError(MapSearchExecutionError):
    """Raised when map tile proxy retrieval fails."""
