"""Scan pipeline helpers (reusable by CLI, web, and workers)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import easyocr
import numpy as np
from tqdm import tqdm

import db
from detection import detect_bib_numbers, Detection, DetectionResult
from preprocessing import PreprocessConfig
from faces import get_face_backend
from faces.artifacts import save_face_snippet, save_face_boxed_preview, save_face_evidence_json
from faces.types import FaceDetection
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

logger = logging.getLogger(__name__)


@dataclass
class ImageInfo:
    """Metadata for an image to be scanned."""

    photo_url: str
    thumbnail_url: str
    album_url: str


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
    thumbnail_url: str,
    album_url: str,
    cache_path: Path,
    skip_existing: bool,
) -> int:
    """Save photo and bib detections to database."""
    photo_id = db.insert_photo(
        conn, album_url, photo_url, thumbnail_url,
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
    thumbnail_url: str,
    album_url: str,
    cache_path: Path,
) -> int:
    """Ensure a photo record exists and return its ID."""
    return db.insert_photo(
        conn, album_url, photo_url, thumbnail_url,
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
    reader: easyocr.Reader | None,
    face_backend,
    conn,
    photo_url: str,
    thumbnail_url: str,
    album_url: str,
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

    photo_id = ensure_photo_record(conn, photo_url, thumbnail_url, album_url, cache_path)

    if run_bib_detection:
        save_detections_to_db(
            conn, result.detections, photo_url, thumbnail_url, album_url, cache_path, skip_existing
        )

    face_detections: list[FaceDetection] = []
    if run_face_detection:
        image_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if image_array is None:
            logger.warning("Failed to decode image for face detection: %s", photo_url)
        else:
            image_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
            boxes = face_backend.detect_faces(image_rgb)
            embeddings = face_backend.embed_faces(image_rgb, boxes)
            model_info = face_backend.model_info()

            paths = ImagePaths.for_cache_path(cache_path)
            paths.ensure_dirs_exist()

            for index, (bbox, embedding) in enumerate(zip(boxes, embeddings)):
                snippet_path = paths.face_snippet_path(index)
                preview_path = paths.face_boxed_path(index)

                snippet_saved = save_face_snippet(image_rgb, bbox, snippet_path)
                preview_saved = save_face_boxed_preview(image_rgb, bbox, preview_path)

                face_detections.append(
                    FaceDetection(
                        face_index=index,
                        bbox=bbox,
                        embedding=embedding,
                        model=model_info,
                        snippet_path=str(snippet_path) if snippet_saved else None,
                        preview_path=str(preview_path) if preview_saved else None,
                    )
                )

            photo_hash = compute_photo_hash(photo_url)
            evidence_path = paths.face_evidence_path(photo_hash)
            bib_evidence = [
                {"bib_number": det.bib_number, "confidence": det.confidence, "bbox": det.bbox}
                for det in result.detections
            ]
            save_face_evidence_json(evidence_path, photo_hash, face_detections, bib_evidence)

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
        reader = easyocr.Reader(["en"], gpu=False)

    face_backend = None
    if run_face_detection:
        logger.info("Initializing face backend...")
        face_backend = get_face_backend()

    conn = db.get_connection()

    logger.info("Scanning images for bib numbers...")
    for info in tqdm(images, total=total, desc="Processing"):
        if skip_existing and db.photo_exists(conn, info.photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            fetch_func = fetch_func_factory(info.photo_url) if fetch_func_factory else None
            image_data, cache_path = load_and_cache_image(info.photo_url, fetch_func)

            bibs_count, faces_count = process_image(
                reader, face_backend, conn,
                info.photo_url, info.thumbnail_url, info.album_url,
                image_data, cache_path, skip_existing,
                run_bib_detection=run_bib_detection,
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
