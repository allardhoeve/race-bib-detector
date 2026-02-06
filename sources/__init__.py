"""
Image source adapters.

This module provides adapters for local image sources.
"""

from .local import scan_local_images
from .cache import get_cache_path, cache_image, load_from_cache

__all__ = [
    "scan_local_images",
    "get_cache_path",
    "cache_image",
    "load_from_cache",
]
