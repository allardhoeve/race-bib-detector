"""Scan service entrypoints for reuse across CLI and web."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import db
from sources import scan_local_images

from .persist import ImageInfo, scan_images

logger = logging.getLogger(__name__)


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


def _compute_content_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_local_directory(
    directory: str,
    album_id: str,
    album_label: str | None,
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

    conn = db.get_connection()
    db.ensure_album(conn, album_id, label=album_label, source_type="local_dir")
    conn.close()

    def make_images():
        for image_path in image_files:
            try:
                content_hash = _compute_content_hash(image_path)
            except OSError as exc:
                logger.warning("Skipping unreadable file %s: %s", image_path, exc)
                continue
            photo_url = f"album:{album_id}:content:{content_hash}"
            yield ImageInfo(
                photo_url=photo_url,
                thumbnail_url=None,
                album_id=album_id,
                source_path=str(image_path),
            )

    def fetch_factory(info: ImageInfo):
        if not info.source_path:
            raise FileNotFoundError("Missing source path for local scan")
        return lambda: Path(info.source_path).read_bytes()

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
            album_id=photo["album_id"],
            source_path=None,
        )

    return scan_images(
        make_images(),
        1,
        skip_existing=False,
        fetch_func_factory=None,
        run_bib_detection=run_bib_detection,
        run_face_detection=run_face_detection,
    )


def _resolve_album_id(
    source: str,
    album_label: str | None,
    album_id: str | None,
) -> tuple[str, str | None]:
    """Resolve album ID and label from explicit args or source path."""
    resolved_id = album_id.strip() if album_id else None
    resolved_label = album_label.strip() if album_label else None
    if resolved_label == "":
        resolved_label = None
    if not resolved_id:
        basis = resolved_label if resolved_label else str(Path(source).resolve())
        resolved_id = db.compute_album_id(basis)
    return resolved_id, resolved_label


def ingest_album(
    source: str,
    limit: int | None = None,
    album_label: str | None = None,
    album_id: str | None = None,
) -> dict:
    """Full pipeline: scan all photos in a directory, then cluster faces."""
    if source.startswith(("http://", "https://")):
        raise ValueError("Remote URLs are not supported. Use a local path.")
    if is_photo_identifier(source):
        raise ValueError(
            f"'{source}' looks like a photo identifier, not a directory. "
            "Use 'album rescan' instead."
        )

    resolved_id, resolved_label = _resolve_album_id(source, album_label, album_id)

    stats = scan_local_directory(
        source,
        album_id=resolved_id,
        album_label=resolved_label,
        limit=limit,
    )

    if stats.get("faces_detected", 0) > 0:
        from faces.clustering import cluster_album_faces

        conn = db.get_connection()
        try:
            cluster_stats = cluster_album_faces(conn, resolved_id)
        finally:
            conn.close()
        stats.update(cluster_stats)

    return stats


def rescan_and_cluster(identifier: str) -> dict:
    """Rescan a single photo and re-cluster faces for its album."""
    conn = db.get_connection()
    try:
        if identifier.isdigit():
            photo = db.get_photo_by_index(conn, int(identifier))
        else:
            photo = db.get_photo_by_hash(conn, identifier)
    finally:
        conn.close()

    if not photo:
        raise ValueError(f"Photo '{identifier}' not found in the database.")

    album_id = photo["album_id"]

    stats = rescan_single_photo(identifier)

    if stats.get("faces_detected", 0) > 0:
        from faces.clustering import cluster_album_faces

        conn = db.get_connection()
        try:
            cluster_stats = cluster_album_faces(conn, album_id)
        finally:
            conn.close()
        stats.update(cluster_stats)

    return stats


