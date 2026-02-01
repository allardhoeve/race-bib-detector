"""
Image caching utilities.

Functions for caching downloaded images locally to avoid re-downloading.
"""

import hashlib
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "cache"


def get_cache_path(photo_url: str) -> Path:
    """Generate a cache file path for a photo URL.

    Args:
        photo_url: URL or path identifier for the photo.

    Returns:
        Path where the cached image should be stored.
    """
    # Use hash of URL for unique filename
    url_hash = hashlib.md5(photo_url.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{url_hash}.jpg"


def cache_image(image_data: bytes, cache_path: Path) -> None:
    """Save image data to cache.

    Args:
        image_data: Raw image bytes.
        cache_path: Path to save the image.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path.write_bytes(image_data)


def load_from_cache(cache_path: Path) -> bytes | None:
    """Load image from cache if it exists.

    Args:
        cache_path: Path to the cached image.

    Returns:
        Image bytes if cached, None otherwise.
    """
    if cache_path.exists():
        return cache_path.read_bytes()
    return None
