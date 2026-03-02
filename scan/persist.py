"""Scan pipeline helpers (reusable by CLI, web, and workers)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TYPE_CHECKING

from tqdm import tqdm

import config
import db
from detection import Detection, DetectionResult
from faces import get_face_backend, get_face_backend_by_name, get_face_embedder
from faces.artifacts import (
    save_face_candidates_preview,
    save_face_snippet,
    save_face_boxed_preview,
    save_face_evidence_json,
)
from faces.types import FaceDetection
from photo import compute_photo_hash, ImagePaths
from pipeline import run_single_photo
from sources import get_cache_path, cache_image, load_from_cache
from utils import (
    get_gray_bbox_path,
    get_candidates_path,
    draw_bounding_boxes_on_gray,
    draw_candidates_on_image,
    get_snippet_path,
    save_bib_snippet,
)
from warnings_utils import suppress_torch_mps_pin_memory_warning

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import easyocr


@dataclass
class _CandidateView:
    """Adapter for save_face_candidates_preview (expects .bbox, .passed, .confidence)."""
    bbox: list
    passed: bool
    confidence: float | None


@dataclass
class ImageInfo:
    """Metadata for an image to be scanned."""

    photo_url: str
    thumbnail_url: str | None
    album_id: str
    source_path: str | None = None


def load_and_cache_image(photo_url: str, fetch_func=None) -> tuple[bytes, Path]:
    """Load image from cache or fetch and cache it."""
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
    """Save visualization artifacts: grayscale bbox image, candidates image, and bib snippets."""
    gray_bbox_path = get_gray_bbox_path(cache_path)
    candidates_path = get_candidates_path(cache_path)

    scaled_detections = result.detections_at_ocr_scale()

    for det, scaled_det in zip(result.detections, scaled_detections):
        snippet_path = get_snippet_path(cache_path, det.bib_number, det.bbox)
        save_bib_snippet(result.ocr_grayscale, scaled_det.bbox, snippet_path)

    draw_bounding_boxes_on_gray(result.ocr_grayscale, scaled_detections, gray_bbox_path)

    if result.all_candidates:
        draw_candidates_on_image(result.ocr_grayscale, result.all_candidates, candidates_path)


def save_detections_to_db(
    conn,
    detections: list[Detection],
    photo_url: str,
    thumbnail_url: str | None,
    album_id: str,
    cache_path: Path,
    skip_existing: bool,
) -> int:
    """Save photo and bib detections to database."""
    photo_id = db.insert_photo(
        conn, album_id, photo_url, thumbnail_url,
        cache_path=str(cache_path)
    )

    if not skip_existing:
        db.delete_bib_detections(conn, photo_id)

    for det in detections:
        db.insert_bib_detection(conn, photo_id, det.bib_number, det.confidence, det.bbox)

    return photo_id


def ensure_photo_record(
    conn,
    photo_url: str,
    thumbnail_url: str | None,
    album_id: str,
    cache_path: Path,
) -> int:
    """Ensure a photo record exists and return its ID."""
    return db.insert_photo(
        conn, album_id, photo_url, thumbnail_url,
        cache_path=str(cache_path)
    )


def save_face_detections_to_db(
    conn,
    face_detections: list[FaceDetection],
    photo_id: int,
    skip_existing: bool,
) -> None:
    """Save face detections to database."""
    if not skip_existing:
        db.delete_face_detections(conn, photo_id)

    for face in face_detections:
        db.insert_face_detection(
            conn,
            photo_id=photo_id,
            face_index=face.face_index,
            bbox=face.bbox,
            embedding=face.embedding,
            model_info=face.model,
            snippet_path=face.snippet_path,
            preview_path=face.preview_path,
        )


def _get_bib_detection_ids(conn, photo_id: int) -> list[int]:
    """Get bib detection IDs for a photo, ordered by insertion."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM bib_detections WHERE photo_id = ? ORDER BY id",
        (photo_id,),
    )
    return [row[0] for row in cursor.fetchall()]


def _get_face_detection_ids(conn, photo_id: int) -> list[int]:
    """Get face detection IDs for a photo, ordered by face_index."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM face_detections WHERE photo_id = ? ORDER BY face_index",
        (photo_id,),
    )
    return [row[0] for row in cursor.fetchall()]


def process_image(
    reader: "easyocr.Reader | None",
    face_backend,
    fallback_face_backend,
    conn,
    photo_url: str,
    thumbnail_url: str | None,
    album_id: str,
    image_data: bytes,
    cache_path: Path,
    skip_existing: bool,
    run_bib_detection: bool,
    run_face_detection: bool,
) -> tuple[int, int]:
    """Process a single image: detect bibs/faces, save artifacts, update database.

    Delegates detection to ``run_single_photo()`` (unified pipeline), then
    persists artifacts and database records.
    """
    if run_bib_detection and reader is None:
        raise ValueError("reader is required when run_bib_detection is True")

    # --- Unified detection ---
    sp = run_single_photo(
        image_data,
        reader=reader,
        run_bibs=run_bib_detection,
        face_backend=face_backend,
        fallback_face_backend=fallback_face_backend,
        run_faces=run_face_detection,
        run_autolink=run_bib_detection and run_face_detection,
    )

    result = sp.bib_result

    # --- Bib artifacts + DB ---
    if run_bib_detection and result.detections:
        save_detection_artifacts(result, cache_path)

    photo_id = ensure_photo_record(conn, photo_url, thumbnail_url, album_id, cache_path)

    if run_bib_detection:
        save_detections_to_db(
            conn, result.detections, photo_url, thumbnail_url, album_id, cache_path, skip_existing
        )

    # --- Face embedding, artifacts + DB ---
    face_detections: list[FaceDetection] = []
    if run_face_detection and sp.face_pixel_bboxes and sp.image_rgb is not None:
        image_rgb = sp.image_rgb
        photo_hash = compute_photo_hash(photo_url)

        embedder = get_face_embedder()
        embedder_model_info = embedder.model_info()
        embeddings = embedder.embed(image_rgb, sp.face_pixel_bboxes)

        paths = ImagePaths.for_cache_path(cache_path)
        paths.ensure_dirs_exist()

        for face_index, (bbox, embedding) in enumerate(zip(sp.face_pixel_bboxes, embeddings)):
            snippet_path = paths.face_snippet_path(face_index)
            preview_path = paths.face_boxed_path(face_index)

            snippet_saved = save_face_snippet(image_rgb, bbox, snippet_path)
            preview_saved = save_face_boxed_preview(image_rgb, bbox, preview_path)

            face_detections.append(
                FaceDetection(
                    face_index=face_index,
                    bbox=bbox,
                    embedding=embedding,
                    model=embedder_model_info,
                    snippet_path=str(snippet_path) if snippet_saved else None,
                    preview_path=str(preview_path) if preview_saved else None,
                )
            )

        evidence_path = paths.face_evidence_path(photo_hash)
        candidates_path = paths.face_candidates_path()
        bib_evidence = [
            {"bib_number": det.bib_number, "confidence": det.confidence, "bbox": det.bbox}
            for det in result.detections
        ]
        # Build adapter views for save_face_candidates_preview (expects .bbox, .passed, .confidence)
        candidate_views = [
            _CandidateView(t.to_pixel_quad(), t.passed, t.confidence)
            for t in sp.face_trace if t.pixel_bbox is not None
        ]
        if candidate_views:
            save_face_candidates_preview(image_rgb, candidate_views, candidates_path)
        save_face_evidence_json(
            evidence_path,
            photo_hash,
            face_detections,
            bib_evidence,
            face_candidates=[t.model_dump() for t in sp.face_trace],
        )

    if run_face_detection:
        save_face_detections_to_db(conn, face_detections, photo_id, skip_existing)

    # --- Autolink persistence ---
    if sp.autolink and sp.autolink.pairs and face_detections:
        # Need to map autolink box pairs back to DB detection IDs.
        # Bib detections are inserted in order → get their IDs
        bib_det_ids = _get_bib_detection_ids(conn, photo_id)
        face_det_ids = _get_face_detection_ids(conn, photo_id)

        db.delete_bib_face_links(conn, photo_id)
        for (bib_box, face_box), prov in zip(sp.autolink.pairs, sp.autolink.provenance):
            try:
                bib_idx = sp.bib_boxes.index(bib_box)
                face_idx = sp.face_boxes.index(face_box)
                if bib_idx < len(bib_det_ids) and face_idx < len(face_det_ids):
                    db.insert_bib_face_link(
                        conn, photo_id,
                        bib_det_ids[bib_idx],
                        face_det_ids[face_idx],
                        prov,
                    )
            except ValueError:
                pass  # box not found in list

    return len(result.detections), len(face_detections)


def scan_images(
    images: Iterator[ImageInfo],
    total: int,
    skip_existing: bool,
    fetch_func_factory=None,
    run_bib_detection: bool = True,
    run_face_detection: bool = True,
) -> dict:
    """Scan images for bib numbers and faces."""
    stats = {
        "photos_found": total,
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
        "faces_detected": 0,
    }

    if total == 0:
        logger.info("No images to process.")
        return stats

    reader = None
    if run_bib_detection:
        logger.info("Initializing EasyOCR...")
        suppress_torch_mps_pin_memory_warning()
        import easyocr as _easyocr
        reader = _easyocr.Reader(["en"], gpu=False)

    face_backend = None
    fallback_face_backend = None
    if run_face_detection:
        logger.info("Initializing face backend...")
        face_backend = get_face_backend()
        if config.FACE_FALLBACK_BACKEND:
            fallback_face_backend = get_face_backend_by_name(config.FACE_FALLBACK_BACKEND)

    conn = db.get_connection()

    logger.info("Scanning images for bib numbers...")
    for info in tqdm(images, total=total, desc="Processing"):
        effective_run_bib = run_bib_detection
        if skip_existing and db.photo_exists(conn, info.photo_url):
            if run_face_detection:
                photo_id = db.get_photo_id_by_url(conn, info.photo_url)
                if photo_id is not None and db.face_detections_exist(conn, photo_id):
                    stats["photos_skipped"] += 1
                    continue
                effective_run_bib = False
            else:
                stats["photos_skipped"] += 1
                continue

        try:
            fetch_func = fetch_func_factory(info) if fetch_func_factory else None
            image_data, cache_path = load_and_cache_image(info.photo_url, fetch_func)

            bibs_count, faces_count = process_image(
                reader, face_backend, fallback_face_backend, conn,
                info.photo_url, info.thumbnail_url, info.album_id,
                image_data, cache_path, skip_existing,
                run_bib_detection=effective_run_bib,
                run_face_detection=run_face_detection,
            )
            stats["bibs_detected"] += bibs_count
            stats["faces_detected"] += faces_count
            stats["photos_scanned"] += 1

        except Exception as e:
            logger.exception("Error processing image: %s", e)
            continue

    conn.close()
    return stats
