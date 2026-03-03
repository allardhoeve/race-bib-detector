"""
Main bib number detection orchestration.

This module ties together all detection components: preprocessing, region
detection, OCR, validation, and filtering.

Composable via ``BibPipelineConfig`` (task-100): three independent axes
control image preparation, candidate finding, and OCR strategy.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image

if TYPE_CHECKING:
    import easyocr

from config import (
    BibPipelineConfig,
    ImagePrepMethod,
    CandidateFindMethod,
    OCRMethod,
    WHITE_REGION_CONFIDENCE_THRESHOLD,
)
from preprocessing import run_pipeline, PreprocessConfig, resize_to_width

from .types import Detection, PipelineResult, BibCandidate
from .regions import find_bib_candidates
from .validation import is_valid_bib_number
from .filtering import filter_small_detections, filter_overlapping_detections


def _run_crop_ocr(
    reader: "easyocr.Reader",
    ocr_image: np.ndarray,
    passed_candidates: list[BibCandidate],
) -> list[Detection]:
    """OCR on each candidate crop (CROP strategy)."""
    all_detections: list[Detection] = []

    for candidate in passed_candidates:
        region = candidate.extract_region(ocr_image)
        results = reader.readtext(region)

        region_detections: list[Detection] = []
        best_bib_conf = 0.0
        for bbox, text, confidence in results:
            cleaned = text.strip().replace(" ", "")

            if is_valid_bib_number(cleaned):
                if confidence > best_bib_conf:
                    best_bib_conf = confidence
                    candidate.ocr_text = cleaned
                    candidate.ocr_confidence = float(confidence)

                if confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
                    bbox_adjusted = [[int(p[0]) + candidate.x, int(p[1]) + candidate.y] for p in bbox]
                    region_detections.append(Detection(
                        bib_number=cleaned,
                        confidence=float(confidence),
                        bbox=bbox_adjusted,
                        source="white_region",
                        source_candidate=candidate,
                    ))

        filtered = filter_small_detections(region_detections, candidate.area)
        all_detections.extend(filtered)

    return all_detections


def _run_full_image_ocr(
    reader: "easyocr.Reader",
    ocr_image: np.ndarray,
) -> list[Detection]:
    """OCR on the full image (FULL_IMAGE strategy)."""
    results = reader.readtext(ocr_image)

    all_detections: list[Detection] = []
    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")

        if is_valid_bib_number(cleaned) and confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
            bbox_native = [[int(coord) for coord in point] for point in bbox]
            all_detections.append(Detection(
                bib_number=cleaned,
                confidence=float(confidence),
                bbox=bbox_native,
                source="full_image",
            ))

    return all_detections


def detect_bib_numbers(
    reader: "easyocr.Reader",
    image_data: bytes,
    preprocess_config: PreprocessConfig | None = None,
    artifact_dir: str | None = None,
    bib_config: BibPipelineConfig | None = None,
) -> PipelineResult:
    """Detect bib numbers in an image using EasyOCR.

    Composable across three axes via ``bib_config``:
    - Image prep: GRAYSCALE (default) or COLOR
    - Candidate finding: GRAYSCALE_THRESHOLD (default), HSV_WHITE, or NONE
    - OCR method: CROP (default) or FULL_IMAGE

    Default config reproduces the committed crop-based behavior.

    Args:
        reader: EasyOCR reader instance.
        image_data: Raw image bytes.
        preprocess_config: Optional preprocessing configuration.
        artifact_dir: Optional directory to save intermediate images.
        bib_config: Pipeline composition config. None = default (crop-based).

    Returns:
        PipelineResult containing detections, candidates, and metadata.
    """
    if bib_config is None:
        bib_config = BibPipelineConfig()

    # Load image from bytes
    image = Image.open(io.BytesIO(image_data))
    if image.mode != "RGB":
        image = image.convert("RGB")
    image_array = np.array(image)

    # --- Image prep axis ---
    # Always run the grayscale preprocessing pipeline (needed for OCR and brightness metrics)
    preprocess_result = run_pipeline(image_array, preprocess_config, artifact_dir=artifact_dir)
    ocr_image = preprocess_result.processed       # grayscale, resized
    ocr_grayscale = preprocess_result.processed
    scale_factor = preprocess_result.scale_factor

    # --- Candidate finding axis ---
    # HSV_WHITE needs a color image at OCR dimensions for coordinate alignment
    if (bib_config.image_prep == ImagePrepMethod.COLOR
            and bib_config.candidate_find == CandidateFindMethod.HSV_WHITE):
        ocr_h, ocr_w = ocr_image.shape[:2]
        candidate_image = cv2.resize(image_array, (ocr_w, ocr_h))
    else:
        candidate_image = ocr_image

    all_candidates = find_bib_candidates(
        candidate_image,
        include_rejected=True,
        method=bib_config.candidate_find,
    )
    passed_candidates = [c for c in all_candidates if c.passed]

    # --- OCR axis ---
    if bib_config.ocr_method == OCRMethod.CROP:
        all_detections = _run_crop_ocr(reader, ocr_image, passed_candidates)
    else:
        all_detections = _run_full_image_ocr(reader, ocr_image)

    # --- Post-processing (shared) ---
    all_detections = filter_overlapping_detections(all_detections)

    # Deduplicate: keep highest confidence for each bib number
    best_detections: dict[str, Detection] = {}
    for det in all_detections:
        if det.bib_number not in best_detections or det.confidence > best_detections[det.bib_number].confidence:
            best_detections[det.bib_number] = det

    final_detections = list(best_detections.values())

    # Map bounding boxes back to original image coordinates if we resized
    if scale_factor != 1.0:
        final_detections = [det.scale_bbox(scale_factor) for det in final_detections]

    # Get dimensions
    orig_h, orig_w = image_array.shape[:2]
    ocr_h, ocr_w = ocr_image.shape[:2]

    # Collect artifact paths from preprocessing
    artifact_paths = dict(preprocess_result.artifact_paths)
    preprocess_metadata = dict(preprocess_result.metadata)

    # Save visualizations if artifact_dir provided
    if artifact_dir:
        from pathlib import Path
        from utils import draw_candidates_on_image, draw_bounding_boxes_on_gray

        candidates_path = f"{artifact_dir}/candidates.jpg"
        draw_candidates_on_image(ocr_image, all_candidates, Path(candidates_path))
        artifact_paths["candidates"] = candidates_path

        detections_path = f"{artifact_dir}/detections.jpg"
        ocr_scale_detections = [det.scale_bbox(1.0 / scale_factor) for det in final_detections] if scale_factor != 1.0 else final_detections
        draw_bounding_boxes_on_gray(ocr_grayscale, ocr_scale_detections, Path(detections_path))
        artifact_paths["detections"] = detections_path

    return PipelineResult(
        detections=final_detections,
        all_candidates=all_candidates,
        ocr_grayscale=ocr_grayscale,
        original_dimensions=(orig_w, orig_h),
        ocr_dimensions=(ocr_w, ocr_h),
        scale_factor=scale_factor,
        artifact_paths=artifact_paths,
        preprocess_metadata=preprocess_metadata,
    )
