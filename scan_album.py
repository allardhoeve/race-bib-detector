#!/usr/bin/env python3
"""Scan images for bib numbers using OCR.

Supports three modes:
1. Google Photos album: Provide a URL to scan a shared album
2. Local directory: Provide a path to scan local image files
3. Single photo rescan: Provide a photo hash (e.g., 6dde41fd) or index (e.g., 47)
"""

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import easyocr
import numpy as np
from PIL import Image
from tqdm import tqdm

import db
from detection import detect_bib_numbers
from preprocessing import PreprocessConfig
from sources import (
    extract_images_from_album,
    scan_local_images,
    get_cache_path,
    cache_image,
    load_from_cache,
)
from sources.cache import CACHE_DIR
from utils import get_gray_bbox_path, draw_bounding_boxes_on_gray, download_image, get_snippet_path, save_bib_snippet


@dataclass
class ImageSource:
    """Represents an image to be processed."""
    photo_url: str  # Unique identifier for the photo
    thumbnail_url: str  # URL/path for thumbnail display
    image_data: bytes  # Raw image bytes
    cache_path: Path  # Where to store/find cached data
    original_size: tuple[int, int]  # (width, height) of original image


def process_image(
    reader: easyocr.Reader,
    conn,
    source: ImageSource,
    album_url: str,
    skip_existing: bool,
) -> int:
    """Process a single image: detect bibs, save artifacts, update database.

    Args:
        reader: EasyOCR reader instance
        conn: Database connection
        source: ImageSource with image data and metadata
        album_url: Album URL for database grouping
        skip_existing: Whether to skip already-scanned photos

    Returns:
        Number of bibs detected
    """
    preprocess_config = PreprocessConfig()  # Uses TARGET_WIDTH from config
    bibs, ocr_grayscale = detect_bib_numbers(reader, source.image_data, preprocess_config)

    # Generate grayscale bounding box image and snippets if detections found
    if bibs and ocr_grayscale is not None:
        gray_bbox_path = get_gray_bbox_path(source.cache_path)
        # Bboxes are in original coordinates, scale down for grayscale
        gray_h, gray_w = ocr_grayscale.shape[:2]
        orig_w, orig_h = source.original_size
        gray_scale = gray_w / orig_w
        scaled_bibs = []
        for bib in bibs:
            scaled_bib = bib.copy()
            scaled_bib["bbox"] = [
                [int(p[0] * gray_scale), int(p[1] * gray_scale)]
                for p in bib["bbox"]
            ]
            scaled_bibs.append(scaled_bib)

            # Save snippet for each detected bib (use bbox hash for unique naming)
            snippet_path = get_snippet_path(source.cache_path, bib["bib_number"], bib["bbox"])
            save_bib_snippet(ocr_grayscale, scaled_bib["bbox"], snippet_path)

        draw_bounding_boxes_on_gray(ocr_grayscale, scaled_bibs, gray_bbox_path)

    # Save to database with cache path
    photo_id = db.insert_photo(
        conn, album_url, source.photo_url, source.thumbnail_url,
        cache_path=str(source.cache_path)
    )

    # Clear old detections when rescanning
    if not skip_existing:
        db.delete_bib_detections(conn, photo_id)

    for bib in bibs:
        db.insert_bib_detection(
            conn,
            photo_id,
            bib["bib_number"],
            bib["confidence"],
            bib["bbox"],
        )

    return len(bibs)


def scan_album(album_url: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a Google Photos album and detect bib numbers.

    Args:
        album_url: URL of the Google Photos album
        skip_existing: Skip photos that have already been scanned
        limit: Maximum number of photos to process (None for all)

    Returns:
        Stats dictionary with counts.
    """
    # Extract images from album
    images = extract_images_from_album(album_url)

    stats = {
        "photos_found": len(images),
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    print(f"Found {len(images)} images")

    if not images:
        print("No images found. The album may be empty or require authentication.")
        return stats

    # Apply limit if specified
    if limit is not None:
        images = images[:limit]
        print(f"Processing limited to {limit} images")

    # Initialize EasyOCR (downloads model on first run)
    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    # Initialize database
    conn = db.get_connection()

    # Process each image
    print("\nScanning images for bib numbers...")
    for img_info in tqdm(images, desc="Processing"):
        photo_url = img_info["photo_url"]
        thumbnail_url = img_info["thumbnail_url"]

        # Skip if already scanned
        if skip_existing and db.photo_exists(conn, photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            # Check cache first, then download
            cache_path = get_cache_path(photo_url)
            image_data = load_from_cache(cache_path)

            if image_data is None:
                image_data = download_image(photo_url)
                cache_image(image_data, cache_path)

            # Get original image dimensions
            decoded = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            orig_h, orig_w = decoded.shape[:2]

            source = ImageSource(
                photo_url=photo_url,
                thumbnail_url=thumbnail_url,
                image_data=image_data,
                cache_path=cache_path,
                original_size=(orig_w, orig_h),
            )

            bibs_count = process_image(reader, conn, source, album_url, skip_existing)
            stats["bibs_detected"] += bibs_count
            stats["photos_scanned"] += 1

        except Exception as e:
            print(f"\nError processing image: {e}")
            continue

    conn.close()
    return stats


def scan_local_directory(directory: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a local directory of images and detect bib numbers.

    Args:
        directory: Path to directory containing images
        skip_existing: Skip photos that have already been scanned
        limit: Maximum number of photos to process (None for all)

    Returns:
        Stats dictionary with counts
    """
    try:
        image_files = scan_local_images(directory)
    except ValueError as e:
        print(f"Error: {e}")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    stats = {
        "photos_found": len(image_files),
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    print(f"Found {len(image_files)} images in {directory}")

    if not image_files:
        print("No images found.")
        return stats

    # Apply limit if specified
    if limit is not None:
        image_files = image_files[:limit]
        print(f"Processing limited to {limit} images")

    # Initialize EasyOCR
    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    # Initialize database
    conn = db.get_connection()

    # Use directory path as "album_url" for database grouping
    album_url = f"local:{directory}"

    # Process each image
    print("\nScanning images for bib numbers...")
    for image_path in tqdm(image_files, desc="Processing"):
        # Use the file path as the photo_url (unique identifier)
        photo_url = str(image_path)

        # Skip if already scanned
        if skip_existing and db.photo_exists(conn, photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            # Read image directly from file
            image_data = image_path.read_bytes()

            # Get original image dimensions
            with Image.open(image_path) as img:
                orig_w, orig_h = img.size

            # Create a cache path based on hash of original file path
            path_hash = hashlib.md5(str(image_path).encode()).hexdigest()[:12]
            cache_path = CACHE_DIR / f"{path_hash}.jpg"

            source = ImageSource(
                photo_url=photo_url,
                thumbnail_url=f"file://{image_path}",
                image_data=image_data,
                cache_path=cache_path,
                original_size=(orig_w, orig_h),
            )

            bibs_count = process_image(reader, conn, source, album_url, skip_existing)
            stats["bibs_detected"] += bibs_count
            stats["photos_scanned"] += 1

        except Exception as e:
            print(f"\nError processing {image_path.name}: {e}")
            continue

    conn.close()
    return stats


def rescan_single_photo(identifier: str) -> dict:
    """Rescan a single photo by hash or index.

    Args:
        identifier: Either a photo hash (e.g., "6dde41fd") or 1-based index (e.g., "47")

    Returns:
        Stats dictionary with counts
    """
    conn = db.get_connection()

    # Determine if identifier is a hash or index
    if identifier.isdigit():
        # It's an index
        index = int(identifier)
        photo = db.get_photo_by_index(conn, index)
        total = db.get_photo_count(conn)
        if not photo:
            conn.close()
            print(f"Error: Photo index {index} not found. Database has {total} photos.")
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        print(f"Found photo {index}/{total}: {photo['photo_hash']}")
    else:
        # It's a hash (or partial hash)
        photo = db.get_photo_by_hash(conn, identifier)
        if not photo:
            conn.close()
            print(f"Error: Photo hash '{identifier}' not found.")
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        print(f"Found photo: {photo['photo_hash']}")

    stats = {
        "photos_found": 1,
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    # Initialize EasyOCR
    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    photo_url = photo["photo_url"]
    is_local = photo_url.startswith("/") or photo_url.startswith("file://")

    try:
        if is_local:
            # Local file
            local_path = photo_url.replace("file://", "") if photo_url.startswith("file://") else photo_url
            image_path = Path(local_path)
            if not image_path.exists():
                print(f"Error: Local file not found: {local_path}")
                conn.close()
                return stats

            image_data = image_path.read_bytes()
            with Image.open(image_path) as img:
                orig_w, orig_h = img.size

            # Create cache path from hash of file path
            path_hash = hashlib.md5(str(image_path).encode()).hexdigest()[:12]
            cache_path = CACHE_DIR / f"{path_hash}.jpg"
            thumbnail_url = f"file://{image_path}"
            album_url = photo["album_url"]
        else:
            # Remote image
            cache_path = get_cache_path(photo_url)
            image_data = load_from_cache(cache_path)

            if image_data is None:
                print("Downloading image...")
                image_data = download_image(photo_url)
                cache_image(image_data, cache_path)

            decoded = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            orig_h, orig_w = decoded.shape[:2]
            thumbnail_url = photo["thumbnail_url"]
            album_url = photo["album_url"]

        source = ImageSource(
            photo_url=photo_url,
            thumbnail_url=thumbnail_url,
            image_data=image_data,
            cache_path=cache_path,
            original_size=(orig_w, orig_h),
        )

        print("Processing image...")
        bibs_count = process_image(reader, conn, source, album_url, skip_existing=False)
        stats["bibs_detected"] = bibs_count
        stats["photos_scanned"] = 1

        print(f"Detected {bibs_count} bib(s)")

    except Exception as e:
        print(f"Error processing photo: {e}")

    conn.close()
    return stats


def is_photo_identifier(source: str) -> bool:
    """Check if source looks like a photo hash or index.

    Photo hashes are 8 hex characters. Indices are numeric.
    """
    # Check if it's a number (index)
    if source.isdigit():
        return True

    # Check if it's an 8-character hex string (hash)
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

    # Determine if source is a URL, local path, or photo identifier
    source = args.source
    is_url = source.startswith("http://") or source.startswith("https://") or "photos.google.com" in source or "photos.app.goo.gl" in source

    if is_url:
        stats = scan_album(source, skip_existing=not args.rescan, limit=args.limit)
    elif is_photo_identifier(source):
        # Single photo rescan by hash or index
        stats = rescan_single_photo(source)
    elif Path(source).exists():
        # Treat as local directory/file
        stats = scan_local_directory(source, skip_existing=not args.rescan, limit=args.limit)
    else:
        # Could be a hash that doesn't look like one, or invalid path
        # Try as photo identifier first
        if len(source) <= 8:
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
