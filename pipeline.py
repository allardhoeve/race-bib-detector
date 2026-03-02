"""Unified single-photo detection pipeline.

Both production (scan/pipeline.py) and benchmarking (benchmarking/runner.py)
delegate to ``run_single_photo()`` so that improvements to detection logic
apply everywhere automatically.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import cv2
import numpy as np

import config
from detection import detect_bib_numbers
from detection.types import DetectionResult
from faces.types import FaceCandidate
from geometry import Bbox, bbox_to_rect, rect_iou
from pipeline_types import AutolinkResult, BibBox, FaceBox, predict_links

if TYPE_CHECKING:
    import easyocr
    from faces import FaceBackend

logger = logging.getLogger(__name__)


@dataclass
class SinglePhotoResult:
    """Complete result from processing one photo through both pipelines."""

    image_dims: tuple[int, int]  # (width, height)

    # Bib detection
    bib_result: DetectionResult
    bib_boxes: list[BibBox]
    bib_detect_time_ms: float

    # Face detection
    face_candidates_all: list[FaceCandidate]
    face_boxes: list[FaceBox]
    face_pixel_bboxes: list[Bbox]
    face_detect_time_ms: float

    # Linking
    autolink: AutolinkResult | None = None

    # Decoded image (for consumers that need it for embedding/artifacts)
    image_rgb: np.ndarray | None = None


def _detections_to_bib_boxes(
    result: DetectionResult,
    img_w: int,
    img_h: int,
) -> list[BibBox]:
    """Convert raw detections to normalised [0,1] BibBox list."""
    if img_w <= 0 or img_h <= 0:
        return []
    boxes: list[BibBox] = []
    for det in result.detections:
        x1, y1, x2, y2 = bbox_to_rect(det.bbox)
        boxes.append(BibBox(
            x=x1 / img_w, y=y1 / img_h,
            w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
            number=det.bib_number,
            confidence=det.confidence,
        ))
    return boxes


def _candidates_to_face_boxes(
    candidates: list[FaceCandidate],
    img_w: int,
    img_h: int,
) -> tuple[list[FaceBox], list[Bbox]]:
    """Convert passed face candidates to normalised FaceBox list and pixel bboxes."""
    face_boxes: list[FaceBox] = []
    pixel_bboxes: list[Bbox] = []
    for cand in candidates:
        if not cand.passed:
            continue
        x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
        face_boxes.append(FaceBox(
            x=x1 / img_w, y=y1 / img_h,
            w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
            confidence=cand.confidence,
        ))
        pixel_bboxes.append(cand.bbox)
    return face_boxes, pixel_bboxes


def _run_face_fallback_chain(
    image_rgb: np.ndarray,
    face_backend: "FaceBackend",
    fallback_face_backend: "FaceBackend | None",
    all_candidates: list[FaceCandidate],
    passed_bboxes: list[Bbox],
) -> tuple[list[FaceCandidate], list[Bbox]]:
    """Apply the DNN low-confidence fallback and backend fallback chain.

    Mutates ``all_candidates`` and ``passed_bboxes`` in place, returning
    the updated lists for convenience.

    This logic was previously in scan/pipeline.py:process_image().
    """
    # Phase 1: DNN low-confidence fallback
    if not passed_bboxes:
        fallback_candidates = [
            c for c in all_candidates
            if c.confidence is not None
            and c.confidence >= config.FACE_DNN_FALLBACK_CONFIDENCE_MIN
        ]
        if fallback_candidates:
            fallback_candidates.sort(
                key=lambda c: c.confidence or 0.0,
                reverse=True,
            )
            fallback_candidates = fallback_candidates[:config.FACE_DNN_FALLBACK_MAX]
            passed_bboxes = [c.bbox for c in fallback_candidates]
            logger.info(
                "Face fallback accepted %d low-confidence candidates (min_conf=%.2f).",
                len(passed_bboxes),
                config.FACE_DNN_FALLBACK_CONFIDENCE_MIN,
            )

    # Phase 2: backend fallback (e.g. Haar when DNN finds too few)
    if (
        fallback_face_backend is not None
        and len(passed_bboxes) < config.FACE_FALLBACK_MIN_FACE_COUNT
    ):
        fb_candidates = fallback_face_backend.detect_face_candidates(image_rgb)
        fb_passed = [c.bbox for c in fb_candidates if c.passed]
        if fb_passed:
            filtered: list[Bbox] = []
            for fb_box in fb_passed:
                fb_rect = bbox_to_rect(fb_box)
                duplicate = any(
                    rect_iou(fb_rect, bbox_to_rect(existing)) >= config.FACE_FALLBACK_IOU_THRESHOLD
                    for existing in passed_bboxes
                )
                if not duplicate:
                    filtered.append(fb_box)
            if filtered:
                filtered = filtered[:config.FACE_FALLBACK_MAX]
                passed_bboxes.extend(filtered)
                all_candidates.extend(fb_candidates)
                logger.info(
                    "Face backend fallback accepted %d candidates via %s.",
                    len(filtered),
                    type(fallback_face_backend).__name__,
                )

    return all_candidates, passed_bboxes


def run_single_photo(
    image_data: bytes,
    *,
    reader: "easyocr.Reader | None" = None,
    detect_fn: Callable | None = None,
    run_bibs: bool = True,
    face_backend: "FaceBackend | None" = None,
    fallback_face_backend: "FaceBackend | None" = None,
    run_faces: bool = True,
    run_autolink: bool = True,
    artifact_dir: str | None = None,
) -> SinglePhotoResult:
    """Run bib + face detection on a single photo.

    This is the ONE function both production and benchmarking call.
    It handles image decoding, bib detection, face detection (with fallback
    chain), coordinate normalisation, and optional autolinking.

    Args:
        image_data: Raw image bytes (JPEG/PNG).
        reader: EasyOCR reader instance (required when run_bibs=True and
            detect_fn is None).
        detect_fn: Custom detection callable for test injection.  Defaults
            to ``detect_bib_numbers``.
        run_bibs: Whether to run bib detection.
        face_backend: Primary face detection backend.
        fallback_face_backend: Secondary face backend for the fallback chain.
        run_faces: Whether to run face detection.
        run_autolink: Whether to predict bib-face links.
        artifact_dir: Directory for debug artifacts (bib detection).

    Returns:
        SinglePhotoResult with all detection outputs.
    """
    # --- Image decode (shared) ---
    image_rgb: np.ndarray | None = None
    img_w, img_h = 0, 0

    if image_data:
        img_array = cv2.imdecode(
            np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
        )
        if img_array is not None:
            image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            img_h, img_w = image_rgb.shape[:2]

    # --- Bib detection ---
    bib_result = DetectionResult(
        detections=[],
        all_candidates=[],
        ocr_grayscale=np.empty((0, 0), dtype=np.uint8),
        original_dimensions=(img_w, img_h),
        ocr_dimensions=(img_w, img_h),
        scale_factor=1.0,
    )
    bib_boxes: list[BibBox] = []
    bib_time_ms = 0.0

    if run_bibs:
        if detect_fn is None:
            detect_fn = detect_bib_numbers
        start = time.time()
        bib_result = detect_fn(reader, image_data, artifact_dir=artifact_dir)
        bib_time_ms = (time.time() - start) * 1000
        bib_w, bib_h = bib_result.original_dimensions
        bib_boxes = _detections_to_bib_boxes(bib_result, bib_w, bib_h)

    # --- Face detection ---
    face_candidates_all: list[FaceCandidate] = []
    face_boxes: list[FaceBox] = []
    face_pixel_bboxes: list[Bbox] = []
    face_time_ms = 0.0

    if run_faces and face_backend is not None and image_rgb is not None:
        start = time.time()
        candidates = face_backend.detect_face_candidates(image_rgb)
        face_time_ms = (time.time() - start) * 1000

        face_candidates_all = list(candidates)
        passed_bboxes = [c.bbox for c in candidates if c.passed]

        # Apply fallback chain
        face_candidates_all, passed_bboxes = _run_face_fallback_chain(
            image_rgb, face_backend, fallback_face_backend,
            face_candidates_all, passed_bboxes,
        )

        # Normalise to FaceBox
        for bbox in passed_bboxes:
            x1, y1, x2, y2 = bbox_to_rect(bbox)
            face_boxes.append(FaceBox(
                x=x1 / img_w, y=y1 / img_h,
                w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
                confidence=next(
                    (c.confidence for c in face_candidates_all if c.bbox == bbox and c.passed),
                    next(
                        (c.confidence for c in face_candidates_all if c.bbox == bbox),
                        None,
                    ),
                ),
            ))
            face_pixel_bboxes.append(bbox)

    # --- Autolink ---
    autolink: AutolinkResult | None = None
    if run_autolink and bib_boxes and face_boxes:
        autolink = predict_links(bib_boxes, face_boxes)

    return SinglePhotoResult(
        image_dims=(img_w, img_h),
        bib_result=bib_result,
        bib_boxes=bib_boxes,
        bib_detect_time_ms=bib_time_ms,
        face_candidates_all=face_candidates_all,
        face_boxes=face_boxes,
        face_pixel_bboxes=face_pixel_bboxes,
        face_detect_time_ms=face_time_ms,
        autolink=autolink,
        image_rgb=image_rgb,
    )
