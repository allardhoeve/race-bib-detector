#!/usr/bin/env python3
"""Scan images for bib numbers using OCR.

Supports three modes:
1. Google Photos album: Provide a URL to scan a shared album
2. Local directory: Provide a path to scan local image files
3. Single photo rescan: Provide a photo hash (e.g., 6dde41fd) or index (e.g., 47)
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import easyocr
import numpy as np
from tqdm import tqdm

import db
from detection import detect_bib_numbers, scale_detections, scale_bbox
from preprocessing import PreprocessConfig
from sources import (
    extract_images_from_album,
    scan_local_images,
    get_cache_path,
    cache_image,
    load_from_cache,
)
from utils import get_gray_bbox_path, draw_bounding_boxes_on_gray, download_image, get_snippet_path, save_bib_snippet


@dataclass
class ImageInfo:
    """Metadata for an image to be scanned."""
    photo_url: str
    thumbnail_url: str
    album_url: str


def load_and_cache_image(photo_url: str, fetch_func=None) -> tuple[bytes, Path]:
    """Load image from cache or fetch and cache it.

    Args:
        photo_url: URL or path identifier for the image
        fetch_func: Optional function to fetch image if not cached.
                   If None and not cached, raises FileNotFoundError.

    Returns:
        Tuple of (image_data, cache_path)

    Raises:
        FileNotFoundError: If image not cached and no fetch_func provided
    """
    cache_path = get_cache_path(photo_url)
    image_data = load_from_cache(cache_path)

    if image_data is None:
        if fetch_func is None:
            raise FileNotFoundError(f"Cached image not found: {cache_path}")
        image_data = fetch_func()
        cache_image(image_data, cache_path)

    return image_data, cache_path


def get_image_dimensions(image_data: bytes) -> tuple[int, int]:
    """Get (width, height) from image bytes."""
    decoded = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    h, w = decoded.shape[:2]
    return w, h


def process_image(
    reader: easyocr.Reader,
    conn,
    photo_url: str,
    thumbnail_url: str,
    album_url: str,
    image_data: bytes,
    cache_path: Path,
    skip_existing: bool,
) -> int:
    """Process a single image: detect bibs, save artifacts, update database.

    Returns:
        Number of bibs detected
    """
    orig_w, orig_h = get_image_dimensions(image_data)

    preprocess_config = PreprocessConfig()
    bibs, ocr_grayscale = detect_bib_numbers(reader, image_data, preprocess_config)

    # Generate grayscale bounding box image and snippets if detections found
    if bibs and ocr_grayscale is not None:
        gray_bbox_path = get_gray_bbox_path(cache_path)
        gray_h, gray_w = ocr_grayscale.shape[:2]
        gray_scale = gray_w / orig_w
        scaled_bibs = scale_detections(bibs, gray_scale)

        for bib, scaled_bib in zip(bibs, scaled_bibs):
            snippet_path = get_snippet_path(cache_path, bib["bib_number"], bib["bbox"])
            save_bib_snippet(ocr_grayscale, scaled_bib["bbox"], snippet_path)

        draw_bounding_boxes_on_gray(ocr_grayscale, scaled_bibs, gray_bbox_path)

    # Save to database
    photo_id = db.insert_photo(
        conn, album_url, photo_url, thumbnail_url,
        cache_path=str(cache_path)
    )

    if not skip_existing:
        db.delete_bib_detections(conn, photo_id)

    for bib in bibs:
        db.insert_bib_detection(conn, photo_id, bib["bib_number"], bib["confidence"], bib["bbox"])

    return len(bibs)


def scan_images(
    images: Iterator[ImageInfo],
    total: int,
    skip_existing: bool,
    fetch_func_factory=None,
) -> dict:
    """Scan images for bib numbers.

    Args:
        images: Iterator of ImageInfo objects
        total: Total number of images (for progress bar)
        skip_existing: Skip photos already in database
        fetch_func_factory: Optional function(photo_url) -> fetch_func.
                           Returns a function to fetch the image if not cached.
                           If None, images must already be cached.

    Returns:
        Stats dictionary
    """
    stats = {
        "photos_found": total,
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    if total == 0:
        print("No images to process.")
        return stats

    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    conn = db.get_connection()

    print("\nScanning images for bib numbers...")
    for info in tqdm(images, total=total, desc="Processing"):
        if skip_existing and db.photo_exists(conn, info.photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            fetch_func = fetch_func_factory(info.photo_url) if fetch_func_factory else None
            image_data, cache_path = load_and_cache_image(info.photo_url, fetch_func)

            bibs_count = process_image(
                reader, conn,
                info.photo_url, info.thumbnail_url, info.album_url,
                image_data, cache_path, skip_existing
            )
            stats["bibs_detected"] += bibs_count
            stats["photos_scanned"] += 1

        except Exception as e:
            print(f"\nError processing image: {e}")
            continue

    conn.close()
    return stats


# =============================================================================
# Source-specific functions (just create ImageInfo iterators)
# =============================================================================

def scan_album(album_url: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a Google Photos album for bib numbers."""
    raw_images = extract_images_from_album(album_url)

    print(f"Found {len(raw_images)} images")
    if not raw_images:
        print("No images found. The album may be empty or require authentication.")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    if limit is not None:
        raw_images = raw_images[:limit]
        print(f"Processing limited to {limit} images")

    def make_images():
        for img in raw_images:
            yield ImageInfo(
                photo_url=img["photo_url"],
                thumbnail_url=img["thumbnail_url"],
                album_url=album_url,
            )

    def fetch_factory(photo_url):
        return lambda: download_image(photo_url)

    return scan_images(make_images(), len(raw_images), skip_existing, fetch_factory)


def scan_local_directory(directory: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a local directory of images for bib numbers."""
    try:
        image_files = scan_local_images(directory)
    except ValueError as e:
        print(f"Error: {e}")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    print(f"Found {len(image_files)} images in {directory}")
    if not image_files:
        print("No images found.")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    if limit is not None:
        image_files = image_files[:limit]
        print(f"Processing limited to {limit} images")

    album_url = f"local:{directory}"

    def make_images():
        for image_path in image_files:
            photo_url = str(image_path)
            yield ImageInfo(
                photo_url=photo_url,
                thumbnail_url=f"file://{image_path}",
                album_url=album_url,
            )

    def fetch_factory(photo_url):
        return lambda: Path(photo_url).read_bytes()

    return scan_images(make_images(), len(image_files), skip_existing, fetch_factory)


def rescan_single_photo(identifier: str) -> dict:
    """Rescan a single photo by hash or index (must be cached)."""
    conn = db.get_connection()

    if identifier.isdigit():
        index = int(identifier)
        photo = db.get_photo_by_index(conn, index)
        total = db.get_photo_count(conn)
        if not photo:
            conn.close()
            print(f"Error: Photo index {index} not found. Database has {total} photos.")
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        print(f"Found photo {index}/{total}: {photo['photo_hash']}")
    else:
        photo = db.get_photo_by_hash(conn, identifier)
        if not photo:
            conn.close()
            print(f"Error: Photo hash '{identifier}' not found.")
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        print(f"Found photo: {photo['photo_hash']}")

    conn.close()

    def make_images():
        yield ImageInfo(
            photo_url=photo["photo_url"],
            thumbnail_url=photo["thumbnail_url"],
            album_url=photo["album_url"],
        )

    # No fetch_factory = must already be cached
    return scan_images(make_images(), 1, skip_existing=False, fetch_func_factory=None)


# =============================================================================
# CLI
# =============================================================================

def is_photo_identifier(source: str) -> bool:
    """Check if source looks like a photo hash or index."""
    if source.isdigit():
        return True
    if len(source) == 8:
        try:
            int(source, 16)
            return True
        except ValueError:
            pass
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Scan images for bib numbers. Supports Google Photos albums, local directories, or single photo rescan."
    )
    parser.add_argument(
        "source",
        help="URL of Google Photos album, path to local directory, photo hash (8 hex chars), or photo index (number)"
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Rescan photos that have already been processed"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of photos to process (default: all)"
    )

    args = parser.parse_args()
    source = args.source

    is_url = source.startswith("http://") or source.startswith("https://") or "photos.google.com" in source or "photos.app.goo.gl" in source

    if is_url:
        stats = scan_album(source, skip_existing=not args.rescan, limit=args.limit)
    elif is_photo_identifier(source):
        stats = rescan_single_photo(source)
    elif Path(source).exists():
        stats = scan_local_directory(source, skip_existing=not args.rescan, limit=args.limit)
    elif len(source) <= 8:
        stats = rescan_single_photo(source)
    else:
        print(f"Error: '{source}' is not a valid URL, path, photo hash, or index.")
        return

    print("\n" + "=" * 50)
    print("Scan Complete!")
    print("=" * 50)
    print(f"Photos found:   {stats['photos_found']}")
    print(f"Photos scanned: {stats['photos_scanned']}")
    print(f"Photos skipped: {stats['photos_skipped']}")
    print(f"Bibs detected:  {stats['bibs_detected']}")
    print("\nResults saved to bibs.db")
    print("Query example: sqlite3 bibs.db \"SELECT * FROM bib_detections LIMIT 10\"")


if __name__ == "__main__":
    main()
