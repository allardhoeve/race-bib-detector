"""Cache cleanup utilities for removing cached artifacts safely."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import db

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
GRAY_BBOX_DIR = CACHE_DIR / "gray_bounding"
CANDIDATES_DIR = CACHE_DIR / "candidates"
SNIPPETS_DIR = CACHE_DIR / "snippets"
FACE_SNIPPETS_DIR = CACHE_DIR / "faces" / "snippets"
FACE_BOXED_DIR = CACHE_DIR / "faces" / "boxed"
FACE_EVIDENCE_DIR = CACHE_DIR / "faces" / "evidence"


def _is_under_cache(path: Path) -> bool:
    try:
        path.resolve().relative_to(CACHE_DIR.resolve())
        return True
    except ValueError:
        return False


def _delete_paths(paths: Iterable[Path], dry_run: bool) -> dict:
    counts = {"deleted": 0, "missing": 0, "skipped": 0}
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if not _is_under_cache(path):
            logger.warning("Skip non-cache path: %s", path)
            counts["skipped"] += 1
            continue
        if not path.exists():
            counts["missing"] += 1
            continue
        if path.is_dir():
            counts["skipped"] += 1
            continue
        if dry_run:
            logger.info("Would delete %s", path)
        else:
            path.unlink()
            logger.info("Deleted %s", path)
        counts["deleted"] += 1
    return counts


def _paths_for_cache_file(cache_filename: str, photo_hash: str | None) -> list[Path]:
    stem = Path(cache_filename).stem
    paths: list[Path] = [
        CACHE_DIR / cache_filename,
        GRAY_BBOX_DIR / cache_filename,
        CANDIDATES_DIR / cache_filename,
    ]

    if SNIPPETS_DIR.exists():
        paths.extend(SNIPPETS_DIR.glob(f"{stem}_bib*.jpg"))
    if FACE_SNIPPETS_DIR.exists():
        paths.extend(FACE_SNIPPETS_DIR.glob(f"{stem}_face*.jpg"))
    if FACE_BOXED_DIR.exists():
        paths.extend(FACE_BOXED_DIR.glob(f"{stem}_face*_boxed.jpg"))
    if photo_hash:
        paths.append(FACE_EVIDENCE_DIR / f"{photo_hash}_faces.json")
    return paths


def delete_album_cache(
    cache_entries: Iterable[dict],
    dry_run: bool = False,
) -> dict:
    """Delete cached artifacts for a list of photo cache entries."""
    paths: list[Path] = []
    for entry in cache_entries:
        cache_path = entry.get("cache_path")
        if not cache_path:
            continue
        cache_filename = Path(cache_path).name
        photo_hash = entry.get("photo_hash")
        paths.extend(_paths_for_cache_file(cache_filename, photo_hash))
    return _delete_paths(paths, dry_run)


def delete_album_cache_by_id(
    album_id: str,
    dry_run: bool = False,
) -> dict:
    conn = db.get_connection()
    cache_entries = db.list_album_cache_entries(conn, album_id)
    conn.close()
    return delete_album_cache(cache_entries, dry_run=dry_run)


def cleanup_unreferenced_cache(dry_run: bool = False) -> dict:
    """Delete cache artifacts that are not referenced in the database."""
    conn = db.get_connection()
    cache_entries = db.list_cache_entries(conn)
    conn.close()

    cache_filenames = {Path(entry["cache_path"]).name for entry in cache_entries if entry.get("cache_path")}
    cache_stems = {Path(filename).stem for filename in cache_filenames}
    photo_hashes = {entry["photo_hash"] for entry in cache_entries if entry.get("photo_hash")}

    paths: list[Path] = []

    if CACHE_DIR.exists():
        for path in CACHE_DIR.glob("*.jpg"):
            if path.name not in cache_filenames:
                paths.append(path)

    if GRAY_BBOX_DIR.exists():
        for path in GRAY_BBOX_DIR.glob("*.jpg"):
            if path.name not in cache_filenames:
                paths.append(path)

    if CANDIDATES_DIR.exists():
        for path in CANDIDATES_DIR.glob("*.jpg"):
            if path.name not in cache_filenames:
                paths.append(path)

    if SNIPPETS_DIR.exists():
        for path in SNIPPETS_DIR.glob("*.jpg"):
            stem = path.name.split("_bib", 1)[0]
            if stem not in cache_stems:
                paths.append(path)

    if FACE_SNIPPETS_DIR.exists():
        for path in FACE_SNIPPETS_DIR.glob("*.jpg"):
            stem = path.name.split("_face", 1)[0]
            if stem not in cache_stems:
                paths.append(path)

    if FACE_BOXED_DIR.exists():
        for path in FACE_BOXED_DIR.glob("*.jpg"):
            stem = path.name.split("_face", 1)[0]
            if stem not in cache_stems:
                paths.append(path)

    if FACE_EVIDENCE_DIR.exists():
        for path in FACE_EVIDENCE_DIR.glob("*_faces.json"):
            photo_hash = path.name.replace("_faces.json", "")
            if photo_hash not in photo_hashes:
                paths.append(path)

    return _delete_paths(paths, dry_run)
