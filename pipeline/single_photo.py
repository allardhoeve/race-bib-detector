"""Unified single-photo detection pipeline.

Both production (scan/persist.py) and benchmarking (benchmarking/runner.py)
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
from config import BibPipelineConfig
from detection import detect_bib_numbers
from detection.types import Detection, DetectionResult
from faces.types import FaceCandidate
from geometry import Bbox, bbox_to_rect, rect_iou
from pipeline.types import BibCandidateTrace, FaceCandidateTrace, TraceLink, predict_links

if TYPE_CHECKING:
    import easyocr
    from faces import FaceBackend
    from faces.embedder import FaceEmbedder

logger = logging.getLogger(__name__)


@dataclass
class SinglePhotoResult:
    """Complete result from processing one photo through both pipelines."""

    image_dims: tuple[int, int]  # (width, height)

    # Bib detection
    bib_result: DetectionResult
    bib_trace: list[BibCandidateTrace]
    bib_detect_time_ms: float

    # Face detection
    face_trace: list[FaceCandidateTrace]
    face_detect_time_ms: float

    # Linking (trace-based, task-095)
    links: list[TraceLink] = field(default_factory=list)

    # Decoded image (for consumers that need it for embedding/artifacts)
    image_rgb: np.ndarray | None = None


def _build_bib_trace(
    result: DetectionResult,
    img_w: int,
    img_h: int,
) -> list[BibCandidateTrace]:
    """Build bib candidate trace from detection result.

    Every candidate gets a trace entry.  Detections without a source
    candidate (test stubs) also get an accepted trace with minimal fields.
    """
    if img_w <= 0 or img_h <= 0:
        return []

    sf = result.scale_factor  # OCR→original scale

    # Map each accepted detection back to its source candidate
    accepted_by_candidate: dict[int, Detection] = {}
    for det in result.detections:
        if det.source_candidate is not None:
            cand_id = id(det.source_candidate)
            accepted_by_candidate[cand_id] = det

    traces: list[BibCandidateTrace] = []

    for cand in result.all_candidates:
        # Normalise candidate bbox from OCR coords to [0, 1]
        nx = (cand.x * sf) / img_w
        ny = (cand.y * sf) / img_h
        nw = (cand.w * sf) / img_w
        nh = (cand.h * sf) / img_h

        cand_id = id(cand)
        det = accepted_by_candidate.get(cand_id)
        is_accepted = det is not None
        bib_number: str | None = None
        det_confidence: float | None = None
        if det is not None:
            bib_number = det.bib_number
            det_confidence = det.confidence
            # Use the tight OCR detection bbox (already in original coords)
            dx1, dy1, dx2, dy2 = bbox_to_rect(det.bbox)
            nx = dx1 / img_w
            ny = dy1 / img_h
            nw = (dx2 - dx1) / img_w
            nh = (dy2 - dy1) / img_h

        trace = BibCandidateTrace(
            x=nx, y=ny, w=nw, h=nh,
            area=cand.area,
            aspect_ratio=cand.aspect_ratio,
            median_brightness=cand.median_brightness,
            mean_brightness=cand.mean_brightness,
            relative_area=cand.relative_area,
            passed_validation=cand.passed,
            rejection_reason=cand.rejection_reason,
            ocr_text=cand.ocr_text,
            ocr_confidence=cand.ocr_confidence,
            accepted=is_accepted,
            bib_number=bib_number,
        )
        traces.append(trace)

    # Also create accepted traces for detections without a source candidate
    # (e.g. from test stubs that don't set source_candidate)
    for det in result.detections:
        if det.source_candidate is None:
            x1, y1, x2, y2 = bbox_to_rect(det.bbox)
            traces.append(BibCandidateTrace(
                x=x1 / img_w, y=y1 / img_h,
                w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
                area=0, aspect_ratio=0.0,
                median_brightness=0.0, mean_brightness=0.0,
                relative_area=0.0, passed_validation=True,
                ocr_text=det.bib_number,
                ocr_confidence=det.confidence,
                accepted=True,
                bib_number=det.bib_number,
            ))

    return traces


def _build_face_trace(
    all_candidates: list[FaceCandidate],
    accepted_bboxes: set[int],
    img_w: int,
    img_h: int,
) -> list[FaceCandidateTrace]:
    """Build face candidate trace.

    ``accepted_bboxes`` is a set of ``id(bbox)`` for bboxes that survived
    the fallback chain.  Every candidate gets a trace entry.
    """
    traces: list[FaceCandidateTrace] = []

    for cand in all_candidates:
        x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
        nx = x1 / img_w
        ny = y1 / img_h
        nw = (x2 - x1) / img_w
        nh = (y2 - y1) / img_h

        is_accepted = id(cand.bbox) in accepted_bboxes

        trace = FaceCandidateTrace(
            x=nx, y=ny, w=nw, h=nh,
            confidence=cand.confidence,
            passed=cand.passed,
            rejection_reason=cand.rejection_reason,
            accepted=is_accepted,
            pixel_bbox=(x1, y1, x2, y2),
        )
        traces.append(trace)

    return traces


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
    face_embedder: "FaceEmbedder | None" = None,
    run_faces: bool = True,
    run_autolink: bool = True,
    artifact_dir: str | None = None,
    bib_config: BibPipelineConfig | None = None,
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
    bib_trace: list[BibCandidateTrace] = []
    bib_time_ms = 0.0

    if run_bibs:
        if detect_fn is None:
            detect_fn = detect_bib_numbers
        start = time.time()
        bib_result = detect_fn(reader, image_data, artifact_dir=artifact_dir, bib_config=bib_config)
        bib_time_ms = (time.time() - start) * 1000
        bib_w, bib_h = bib_result.original_dimensions
        bib_trace = _build_bib_trace(bib_result, bib_w, bib_h)

    # --- Face detection ---
    face_trace: list[FaceCandidateTrace] = []
    face_time_ms = 0.0

    if run_faces and face_backend is not None and image_rgb is not None:
        start = time.time()
        candidates = face_backend.detect_face_candidates(image_rgb)
        face_time_ms = (time.time() - start) * 1000

        all_candidates = list(candidates)
        passed_bboxes = [c.bbox for c in candidates if c.passed]

        # Apply fallback chain
        all_candidates, passed_bboxes = _run_face_fallback_chain(
            image_rgb, face_backend, fallback_face_backend,
            all_candidates, passed_bboxes,
        )

        # Build trace
        accepted_bbox_ids = {id(bbox) for bbox in passed_bboxes}
        face_trace = _build_face_trace(
            all_candidates, accepted_bbox_ids, img_w, img_h,
        )

    # --- Face embedding ---
    if face_embedder is not None and face_trace and image_rgb is not None:
        accepted = [t for t in face_trace if t.accepted and t.pixel_bbox]
        if accepted:
            bboxes = [t.to_pixel_quad() for t in accepted]
            embeddings = face_embedder.embed(image_rgb, bboxes)
            for trace, emb in zip(accepted, embeddings):
                trace.embedding = emb.tolist()

    # --- Autolink ---
    links: list[TraceLink] = []
    if run_autolink:
        accepted_bibs = [t for t in bib_trace if t.accepted]
        accepted_faces = [t for t in face_trace if t.accepted]
        if accepted_bibs and accepted_faces:
            links = predict_links(accepted_bibs, accepted_faces)

    return SinglePhotoResult(
        image_dims=(img_w, img_h),
        bib_result=bib_result,
        bib_trace=bib_trace,
        bib_detect_time_ms=bib_time_ms,
        face_trace=face_trace,
        face_detect_time_ms=face_time_ms,
        links=links,
        image_rgb=image_rgb,
    )
