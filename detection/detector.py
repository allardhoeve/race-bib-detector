"""
Main bib number detection orchestration.

This module ties together all detection components: preprocessing, region
detection, OCR, validation, and filtering.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    import easyocr

from config import (
    WHITE_REGION_CONFIDENCE_THRESHOLD,
)
from preprocessing import run_pipeline, PreprocessConfig

from .types import Detection, PipelineResult, BibCandidate
from .regions import find_bib_candidates
from .validation import is_valid_bib_number
from .filtering import filter_small_detections, filter_overlapping_detections


def detect_bib_numbers(
    reader: easyocr.Reader,
    image_data: bytes,
    preprocess_config: PreprocessConfig | None = None,
    artifact_dir: str | None = None,
) -> PipelineResult:
    """Detect bib numbers in an image using EasyOCR.

    Focuses on white rectangular regions (typical bib appearance) and
    filters for valid bib number patterns.

    Args:
        reader: EasyOCR reader instance.
        image_data: Raw image bytes.
        preprocess_config: Optional preprocessing configuration.
        artifact_dir: Optional directory to save intermediate images and visualizations.

    Returns:
        PipelineResult containing detections, candidates, and metadata for coordinate mapping.
    """
    # Load image from bytes
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Convert to numpy array
    image_array = np.array(image)

    # Apply preprocessing pipeline (grayscale + resize)
    preprocess_result = run_pipeline(image_array, preprocess_config, artifact_dir=artifact_dir)

    # Use processed grayscale image for all detection
    # The pipeline produces a grayscale, resized image ready for OCR
    ocr_image = preprocess_result.processed
    ocr_grayscale = preprocess_result.processed  # Same image, it's already grayscale
    scale_factor = preprocess_result.scale_factor

    # Find candidate bib regions on the OCR image (resized if preprocessing enabled)
    # Include rejected candidates for full transparency in PipelineResult
    all_candidates = find_bib_candidates(ocr_image, include_rejected=True)
    passed_candidates = [c for c in all_candidates if c.passed]

    all_detections = []

    # OCR on each candidate bib region (only passed ones)
    for candidate in passed_candidates:
        region = candidate.extract_region(ocr_image)
        results = reader.readtext(region)

        region_detections: list[Detection] = []
        for bbox, text, confidence in results:
            cleaned = text.strip().replace(" ", "")

            if is_valid_bib_number(cleaned) and confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
                # Adjust bbox coordinates to full OCR image (before scaling back)
                bbox_adjusted = [[int(p[0]) + candidate.x, int(p[1]) + candidate.y] for p in bbox]
                region_detections.append(Detection(
                    bib_number=cleaned,
                    confidence=float(confidence),
                    bbox=bbox_adjusted,
                    source="white_region",
                    source_candidate=candidate,
                ))

        # Filter out tiny detections relative to this candidate region
        filtered = filter_small_detections(region_detections, candidate.area)
        all_detections.extend(filtered)

    # Filter overlapping detections (e.g., "620" vs "6", "20")
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

    # Save candidates and detections visualizations if artifact_dir provided
    if artifact_dir:
        from pathlib import Path
        from utils import draw_candidates_on_image, draw_bounding_boxes_on_gray

        # Save candidates visualization
        candidates_path = f"{artifact_dir}/candidates.jpg"
        draw_candidates_on_image(ocr_image, all_candidates, Path(candidates_path))
        artifact_paths["candidates"] = candidates_path

        # Save detections visualization (use detections at OCR scale for visualization)
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
