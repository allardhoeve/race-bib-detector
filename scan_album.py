#!/usr/bin/env python3
"""Scan images for bib numbers using OCR.

Supports three modes:
1. Google Photos album: Provide a URL to scan a shared album
2. Local directory: Provide a path to scan local image files
3. Single photo rescan: Provide a photo hash (e.g., 6dde41fd) or index (e.g., 47)
"""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import easyocr
import numpy as np
from tqdm import tqdm

import db
from detection import detect_bib_numbers, Detection, DetectionResult
from preprocessing import PreprocessConfig
from sources import (
    extract_images_from_album,
    scan_local_images,
    get_cache_path,
    cache_image,
    load_from_cache,
)
from logging_utils import configure_logging, LOG_LEVEL_CHOICES
from utils import (
    get_gray_bbox_path,
    get_candidates_path,
    draw_bounding_boxes_on_gray,
    draw_candidates_on_image,
    download_image,
    get_snippet_path,
    save_bib_snippet,
)

logger = logging.getLogger(__name__)


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


def save_detection_artifacts(
    result: DetectionResult,
    cache_path: Path,
) -> None:
    """Save visualization artifacts: grayscale bbox image, candidates image, and bib snippets.

    Args:
        result: DetectionResult (PipelineResult) from detect_bib_numbers
        cache_path: Path to cached image file
    """
    gray_bbox_path = get_gray_bbox_path(cache_path)
    candidates_path = get_candidates_path(cache_path)

    # Get detections scaled to OCR image coordinates for visualization
    scaled_detections = result.detections_at_ocr_scale()

    for det, scaled_det in zip(result.detections, scaled_detections):
        snippet_path = get_snippet_path(cache_path, det.bib_number, det.bbox)
        save_bib_snippet(result.ocr_grayscale, scaled_det.bbox, snippet_path)

    draw_bounding_boxes_on_gray(result.ocr_grayscale, scaled_detections, gray_bbox_path)

    # Save candidates visualization (shows all candidates: passed=green, rejected=red)
    if result.all_candidates:
        draw_candidates_on_image(result.ocr_grayscale, result.all_candidates, candidates_path)


def save_detections_to_db(
    conn,
    detections: list[Detection],
    photo_url: str,
    thumbnail_url: str,
    album_url: str,
    cache_path: Path,
    skip_existing: bool,
) -> int:
    """Save photo and bib detections to database.

    Args:
        conn: Database connection
        detections: List of Detection objects
        photo_url: URL of the photo
        thumbnail_url: URL of the thumbnail
        album_url: URL of the album
        cache_path: Path to cached image file
        skip_existing: If False, delete existing detections before inserting

    Returns:
        Database photo_id
    """
    photo_id = db.insert_photo(
        conn, album_url, photo_url, thumbnail_url,
        cache_path=str(cache_path)
    )

    if not skip_existing:
        db.delete_bib_detections(conn, photo_id)

    for det in detections:
        db.insert_bib_detection(conn, photo_id, det.bib_number, det.confidence, det.bbox)

    return photo_id


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
    preprocess_config = PreprocessConfig()
    result = detect_bib_numbers(reader, image_data, preprocess_config)

    if result.detections:
        save_detection_artifacts(result, cache_path)

    save_detections_to_db(
        conn, result.detections, photo_url, thumbnail_url, album_url, cache_path, skip_existing
    )

    return len(result.detections)


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
        logger.info("No images to process.")
        return stats

    logger.info("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    conn = db.get_connection()

    logger.info("Scanning images for bib numbers...")
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
            logger.exception("Error processing image: %s", e)
            continue

    conn.close()
    return stats


# =============================================================================
# Source-specific functions (just create ImageInfo iterators)
# =============================================================================

def scan_album(album_url: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a Google Photos album for bib numbers."""
    raw_images = extract_images_from_album(album_url)

    logger.info("Found %s images", len(raw_images))
    if not raw_images:
        logger.warning("No images found. The album may be empty or require authentication.")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    if limit is not None:
        raw_images = raw_images[:limit]
        logger.info("Processing limited to %s images", limit)

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
        logger.error("%s", e)
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    logger.info("Found %s images in %s", len(image_files), directory)
    if not image_files:
        logger.warning("No images found.")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    if limit is not None:
        image_files = image_files[:limit]
        logger.info("Processing limited to %s images", limit)

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
            logger.error("Photo index %s not found. Database has %s photos.", index, total)
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        logger.info("Found photo %s/%s: %s", index, total, photo["photo_hash"])
    else:
        photo = db.get_photo_by_hash(conn, identifier)
        if not photo:
            conn.close()
            logger.error("Photo hash '%s' not found.", identifier)
            return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}
        logger.info("Found photo: %s", photo["photo_hash"])

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


def run_scan(source: str, rescan: bool = False, limit: int | None = None) -> int:
    """Run scan on a source (URL, path, or photo identifier).

    Args:
        source: URL, local path, photo hash, or photo index
        rescan: If True, rescan already processed photos
        limit: Maximum number of photos to process

    Returns:
        Exit code (0 for success)
    """
    is_url = source.startswith("http://") or source.startswith("https://") or "photos.google.com" in source or "photos.app.goo.gl" in source

    if is_url:
        stats = scan_album(source, skip_existing=not rescan, limit=limit)
    elif is_photo_identifier(source):
        stats = rescan_single_photo(source)
    elif Path(source).exists():
        stats = scan_local_directory(source, skip_existing=not rescan, limit=limit)
    elif len(source) <= 8:
        stats = rescan_single_photo(source)
    else:
        logger.error("'%s' is not a valid URL, path, photo hash, or index.", source)
        return 1

    logger.info("%s", "=" * 50)
    logger.info("Scan Complete!")
    logger.info("%s", "=" * 50)
    logger.info("Photos found:   %s", stats["photos_found"])
    logger.info("Photos scanned: %s", stats["photos_scanned"])
    logger.info("Photos skipped: %s", stats["photos_skipped"])
    logger.info("Bibs detected:  %s", stats["bibs_detected"])
    logger.info("Results saved to bibs.db")
    logger.info("Query example: sqlite3 bibs.db \"SELECT * FROM bib_detections LIMIT 10\"")
    return 0


def build_parser() -> argparse.ArgumentParser:
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
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        help="Set log verbosity (debug, info, warning, error, critical)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (use -vv for more detail)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="count",
        default=0,
        help="Reduce log verbosity (use -qq for errors only)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of photos to process (default: all)"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)
    return run_scan(args.source, rescan=args.rescan, limit=args.limit)


if __name__ == "__main__":
    main()
