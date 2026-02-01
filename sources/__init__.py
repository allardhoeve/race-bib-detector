"""
Image source adapters.

This module provides adapters for different image sources:
- Google Photos albums (via web scraping)
- Local directories

Each source yields images in a common format for processing.
"""

from .google_photos import extract_images_from_album
from .local import scan_local_images
from .cache import get_cache_path, cache_image, load_from_cache

__all__ = [
    "extract_images_from_album",
    "scan_local_images",
    "get_cache_path",
    "cache_image",
    "load_from_cache",
]
