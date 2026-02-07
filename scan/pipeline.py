"""Scan pipeline helpers (reusable by CLI, web, and workers)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from tqdm import tqdm
from typing import TYPE_CHECKING

import config
import db
from detection import detect_bib_numbers, Detection, DetectionResult
from preprocessing import PreprocessConfig
from faces import get_face_backend, get_face_backend_by_name
from faces.artifacts import (
    save_face_candidates_preview,
    save_face_snippet,
    save_face_boxed_preview,
    save_face_evidence_json,
)
from faces.types import FaceDetection
from geometry import bbox_to_rect, rect_iou
from photo import compute_photo_hash, ImagePaths
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
    """Process a single image: detect bibs/faces, save artifacts, update database."""
    result = DetectionResult(
        detections=[],
        all_candidates=[],
        ocr_grayscale=np.empty((0, 0), dtype=np.uint8),
        original_dimensions=(0, 0),
        ocr_dimensions=(0, 0),
        scale_factor=1.0,
    )

    if run_bib_detection:
        if reader is None:
            raise ValueError("reader is required when run_bib_detection is True")
        preprocess_config = PreprocessConfig()
        result = detect_bib_numbers(reader, image_data, preprocess_config)

        if result.detections:
            save_detection_artifacts(result, cache_path)

    photo_id = ensure_photo_record(conn, photo_url, thumbnail_url, album_id, cache_path)

    if run_bib_detection:
        save_detections_to_db(
            conn, result.detections, photo_url, thumbnail_url, album_id, cache_path, skip_existing
        )

    face_detections: list[FaceDetection] = []
    if run_face_detection:
        image_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if image_array is None:
            logger.warning("Failed to decode image for face detection: %s", photo_url)
        else:
            image_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
            candidates = face_backend.detect_face_candidates(image_rgb)
            boxes = [candidate.bbox for candidate in candidates if candidate.passed]
            photo_hash = compute_photo_hash(photo_url)
            if not boxes:
                fallback_candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.confidence is not None
                    and candidate.confidence >= config.FACE_DNN_FALLBACK_CONFIDENCE_MIN
                ]
                if fallback_candidates:
                    fallback_candidates.sort(
                        key=lambda candidate: candidate.confidence or 0.0,
                        reverse=True,
                    )
                    fallback_candidates = fallback_candidates[: config.FACE_DNN_FALLBACK_MAX]
                    boxes = [candidate.bbox for candidate in fallback_candidates]
                    logger.info(
                        "Face fallback accepted %d candidates for %s (min_conf=%.2f).",
                        len(boxes),
                        photo_hash,
                        config.FACE_DNN_FALLBACK_CONFIDENCE_MIN,
                    )
            all_candidates = list(candidates)
            detections_by_backend: list[tuple[object, list]] = []
            if boxes:
                detections_by_backend.append((face_backend, boxes))

            if (
                fallback_face_backend is not None
                and len(boxes) < config.FACE_FALLBACK_MIN_FACE_COUNT
            ):
                fallback_candidates = fallback_face_backend.detect_face_candidates(image_rgb)
                fallback_boxes = [candidate.bbox for candidate in fallback_candidates if candidate.passed]
                if fallback_boxes:
                    filtered_boxes: list = []
                    for fallback_box in fallback_boxes:
                        fallback_rect = bbox_to_rect(fallback_box)
                        duplicate = False
                        for existing_box in boxes:
                            existing_rect = bbox_to_rect(existing_box)
                            iou = rect_iou(fallback_rect, existing_rect)
                            if iou >= config.FACE_FALLBACK_IOU_THRESHOLD:
                                duplicate = True
                                break
                        if not duplicate:
                            filtered_boxes.append(fallback_box)
                    if filtered_boxes:
                        filtered_boxes = filtered_boxes[: config.FACE_FALLBACK_MAX]
                        detections_by_backend.append((fallback_face_backend, filtered_boxes))
                        all_candidates.extend(fallback_candidates)
                        logger.info(
                            "Face backend fallback accepted %d candidates for %s via %s.",
                            len(filtered_boxes),
                            photo_hash,
                            type(fallback_face_backend).__name__,
                        )

            embeddings_by_backend: list[tuple[list, list, object]] = []
            for backend, backend_boxes in detections_by_backend:
                embeddings = backend.embed_faces(image_rgb, backend_boxes)
                model_info = backend.model_info()
                embeddings_by_backend.append((backend_boxes, embeddings, model_info))

            paths = ImagePaths.for_cache_path(cache_path)
            paths.ensure_dirs_exist()

            face_index = 0
            for backend_boxes, embeddings, model_info in embeddings_by_backend:
                for bbox, embedding in zip(backend_boxes, embeddings):
                    snippet_path = paths.face_snippet_path(face_index)
                    preview_path = paths.face_boxed_path(face_index)

                    snippet_saved = save_face_snippet(image_rgb, bbox, snippet_path)
                    preview_saved = save_face_boxed_preview(image_rgb, bbox, preview_path)

                    face_detections.append(
                        FaceDetection(
                            face_index=face_index,
                            bbox=bbox,
                            embedding=embedding,
                            model=model_info,
                            snippet_path=str(snippet_path) if snippet_saved else None,
                            preview_path=str(preview_path) if preview_saved else None,
                        )
                    )
                    face_index += 1

            evidence_path = paths.face_evidence_path(photo_hash)
            candidates_path = paths.face_candidates_path()
            bib_evidence = [
                {"bib_number": det.bib_number, "confidence": det.confidence, "bbox": det.bbox}
                for det in result.detections
            ]
            if all_candidates:
                save_face_candidates_preview(image_rgb, all_candidates, candidates_path)
            save_face_evidence_json(
                evidence_path,
                photo_hash,
                face_detections,
                bib_evidence,
                face_candidates=all_candidates,
            )

        save_face_detections_to_db(conn, face_detections, photo_id, skip_existing)

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
