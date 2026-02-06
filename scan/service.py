"""Scan service entrypoints for reuse across CLI and web."""

from __future__ import annotations

import logging
from pathlib import Path

import db
from sources import extract_images_from_album, scan_local_images
from utils import download_image

from .pipeline import ImageInfo, scan_images

logger = logging.getLogger(__name__)


def resolve_face_mode(
    faces_only: bool,
    no_faces: bool,
) -> tuple[bool, bool]:
    """Resolve bib/face mode flags into run_bib_detection/run_face_detection."""
    if faces_only and no_faces:
        raise ValueError("faces_only and no_faces cannot both be True")
    run_bib_detection = not faces_only
    run_face_detection = not no_faces
    return run_bib_detection, run_face_detection


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


def scan_album(
    album_url: str,
    skip_existing: bool = True,
    limit: int | None = None,
    run_bib_detection: bool = True,
    run_face_detection: bool = True,
) -> dict:
    """Scan a Google Photos album for bib numbers and faces."""
    raw_images = extract_images_from_album(album_url)

    logger.info("Found %s images", len(raw_images))
    if not raw_images:
        logger.warning("No images found. The album may be empty or require authentication.")
        return {
            "photos_found": 0,
            "photos_scanned": 0,
            "photos_skipped": 0,
            "bibs_detected": 0,
            "faces_detected": 0,
        }

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

    return scan_images(
        make_images(),
        len(raw_images),
        skip_existing,
        fetch_factory,
        run_bib_detection=run_bib_detection,
        run_face_detection=run_face_detection,
    )


def scan_local_directory(
    directory: str,
    skip_existing: bool = True,
    limit: int | None = None,
    run_bib_detection: bool = True,
    run_face_detection: bool = True,
) -> dict:
    """Scan a local directory of images for bib numbers and faces."""
    try:
        image_files = scan_local_images(directory)
    except ValueError as e:
        logger.error("%s", e)
        return {
            "photos_found": 0,
            "photos_scanned": 0,
            "photos_skipped": 0,
            "bibs_detected": 0,
            "faces_detected": 0,
        }

    logger.info("Found %s images in %s", len(image_files), directory)
    if not image_files:
        logger.warning("No images found.")
        return {
            "photos_found": 0,
            "photos_scanned": 0,
            "photos_skipped": 0,
            "bibs_detected": 0,
            "faces_detected": 0,
        }

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

    return scan_images(
        make_images(),
        len(image_files),
        skip_existing,
        fetch_factory,
        run_bib_detection=run_bib_detection,
        run_face_detection=run_face_detection,
    )


def rescan_single_photo(
    identifier: str,
    run_bib_detection: bool = True,
    run_face_detection: bool = True,
) -> dict:
    """Rescan a single photo by hash or index (must be cached)."""
    conn = db.get_connection()

    if identifier.isdigit():
        index = int(identifier)
        photo = db.get_photo_by_index(conn, index)
        total = db.get_photo_count(conn)
        if not photo:
            conn.close()
            logger.error("Photo index %s not found. Database has %s photos.", index, total)
            return {
                "photos_found": 0,
                "photos_scanned": 0,
                "photos_skipped": 0,
                "bibs_detected": 0,
                "faces_detected": 0,
            }
        logger.info("Found photo %s/%s: %s", index, total, photo["photo_hash"])
    else:
        photo = db.get_photo_by_hash(conn, identifier)
        if not photo:
            conn.close()
            logger.error("Photo hash '%s' not found.", identifier)
            return {
                "photos_found": 0,
                "photos_scanned": 0,
                "photos_skipped": 0,
                "bibs_detected": 0,
                "faces_detected": 0,
            }
        logger.info("Found photo: %s", photo["photo_hash"])

    conn.close()

    def make_images():
        yield ImageInfo(
            photo_url=photo["photo_url"],
            thumbnail_url=photo["thumbnail_url"],
            album_url=photo["album_url"],
        )

    return scan_images(
        make_images(),
        1,
        skip_existing=False,
        fetch_func_factory=None,
        run_bib_detection=run_bib_detection,
        run_face_detection=run_face_detection,
    )


def run_scan(
    source: str,
    rescan: bool = False,
    limit: int | None = None,
    faces_only: bool = False,
    no_faces: bool = False,
) -> dict:
    """Run scan on a source (URL, path, or photo identifier)."""
    is_url = (
        source.startswith("http://")
        or source.startswith("https://")
        or "photos.google.com" in source
        or "photos.app.goo.gl" in source
    )
    run_bib_detection, run_face_detection = resolve_face_mode(faces_only, no_faces)
    if not run_bib_detection and not run_face_detection:
        raise ValueError("At least one of bib detection or face detection must be enabled.")

    if is_url:
        stats = scan_album(
            source,
            skip_existing=not rescan,
            limit=limit,
            run_bib_detection=run_bib_detection,
            run_face_detection=run_face_detection,
        )
    elif is_photo_identifier(source):
        stats = rescan_single_photo(
            source,
            run_bib_detection=run_bib_detection,
            run_face_detection=run_face_detection,
        )
    elif Path(source).exists():
        stats = scan_local_directory(
            source,
            skip_existing=not rescan,
            limit=limit,
            run_bib_detection=run_bib_detection,
            run_face_detection=run_face_detection,
        )
    elif len(source) <= 8:
        stats = rescan_single_photo(
            source,
            run_bib_detection=run_bib_detection,
            run_face_detection=run_face_detection,
        )
    else:
        raise ValueError(f"'{source}' is not a valid URL, path, photo hash, or index.")

    return stats
