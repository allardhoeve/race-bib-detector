"""Shared utility functions for bib number recognizer."""

import re
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent / "cache"


def clean_photo_url(url: str) -> dict:
    """Clean a Google Photos URL and return base, full-res, and thumbnail URLs.

    Returns dict with keys: base_url, photo_url, thumbnail_url
    """
    # Remove size parameters to get base URL
    base_url = re.sub(r'=w\d+.*$', '', url)
    base_url = re.sub(r'=s\d+.*$', '', base_url)

    return {
        "base_url": base_url,
        "photo_url": base_url + "=w2048",  # Reasonable size for OCR
        "thumbnail_url": base_url + "=w400",
    }


def get_full_res_url(photo_url: str) -> str:
    """Convert a photo URL to full resolution (original size)."""
    base_url = re.sub(r'=w\d+.*$', '', photo_url)
    base_url = re.sub(r'=s\d+.*$', '', base_url)
    return base_url + "=w0"


def download_image(url: str, timeout: int = 30) -> bytes:
    """Download an image and return its bytes."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def download_image_to_file(url: str, output_path: Path, timeout: int = 60) -> bool:
    """Download an image to a file path. Returns True on success."""
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"\nError downloading {url}: {e}")
        return False
