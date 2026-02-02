"""
Main bib number detection orchestration.

This module ties together all detection components: preprocessing, region
detection, OCR, validation, and filtering.
"""

import io

import easyocr
import numpy as np
from PIL import Image

from config import (
    WHITE_REGION_CONFIDENCE_THRESHOLD,
    FULL_IMAGE_CONFIDENCE_THRESHOLD,
    MEDIAN_BRIGHTNESS_THRESHOLD,
    MEAN_BRIGHTNESS_THRESHOLD,
)
from preprocessing import run_pipeline, PreprocessConfig

from .types import Detection
from .regions import find_white_regions
from .validation import is_valid_bib_number
from .filtering import filter_small_detections, filter_overlapping_detections


def detect_bib_numbers(
    reader: easyocr.Reader,
    image_data: bytes,
    preprocess_config: PreprocessConfig | None = None,
) -> tuple[list[Detection], np.ndarray | None]:
    """Detect bib numbers in an image using EasyOCR.

    Focuses on white rectangular regions (typical bib appearance) and
    filters for valid bib number patterns.

    Args:
        reader: EasyOCR reader instance.
        image_data: Raw image bytes.
        preprocess_config: Optional preprocessing configuration.

    Returns:
        Tuple of (list of Detection objects, grayscale image used for OCR).
    """
    # Load image from bytes
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Convert to numpy array
    image_array = np.array(image)

    # Apply preprocessing pipeline
    preprocess_result = run_pipeline(image_array, preprocess_config)

    # Use resized image for OCR if available (more consistent kernel behavior)
    if preprocess_result.resized is not None:
        ocr_image = preprocess_result.resized
        ocr_grayscale = preprocess_result.resized_grayscale
        scale_factor = preprocess_result.scale_factor
    else:
        ocr_image = image_array
        ocr_grayscale = preprocess_result.grayscale
        scale_factor = 1.0

    # Find candidate white regions on the OCR image (resized if preprocessing enabled)
    white_regions = find_white_regions(ocr_image)

    all_detections = []

    if white_regions:
        # OCR only on candidate regions
        for (x, y, w, h) in white_regions:
            region_area = w * h
            region = ocr_image[y:y+h, x:x+w]
            results = reader.readtext(region)

            region_detections: list[Detection] = []
            for bbox, text, confidence in results:
                cleaned = text.strip().replace(" ", "")

                if is_valid_bib_number(cleaned) and confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
                    # Adjust bbox coordinates to full OCR image (before scaling back)
                    bbox_adjusted = [[int(p[0]) + x, int(p[1]) + y] for p in bbox]
                    region_detections.append(Detection(
                        bib_number=cleaned,
                        confidence=float(confidence),
                        bbox=bbox_adjusted,
                    ))

            # Filter out tiny detections relative to this white region
            filtered = filter_small_detections(region_detections, region_area)
            all_detections.extend(filtered)

    # Also run OCR on full image as fallback (in case region detection missed something)
    # For full image scan, we validate brightness to filter false positives
    results = reader.readtext(ocr_image)
    gray_for_brightness = preprocess_result.resized_grayscale if preprocess_result.resized_grayscale is not None else preprocess_result.grayscale
    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")

        if is_valid_bib_number(cleaned) and confidence > FULL_IMAGE_CONFIDENCE_THRESHOLD:
            bbox_native = [[int(coord) for coord in point] for point in bbox]

            # Check brightness of detected region to filter false positives
            # (e.g., light text on dark backgrounds like Adidas logos)
            x_coords = [p[0] for p in bbox_native]
            y_coords = [p[1] for p in bbox_native]
            x_min, x_max = max(0, min(x_coords)), min(gray_for_brightness.shape[1], max(x_coords))
            y_min, y_max = max(0, min(y_coords)), min(gray_for_brightness.shape[0], max(y_coords))

            if x_max > x_min and y_max > y_min:
                region = gray_for_brightness[y_min:y_max, x_min:x_max]
                median_brightness = np.median(region)
                mean_brightness = np.mean(region)
                # Skip dark regions with scattered bright pixels
                if median_brightness < MEDIAN_BRIGHTNESS_THRESHOLD or mean_brightness < MEAN_BRIGHTNESS_THRESHOLD:
                    continue

            all_detections.append(Detection(
                bib_number=cleaned,
                confidence=float(confidence),
                bbox=bbox_native,
            ))

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

    # Return detections and the grayscale image used (at OCR resolution for visualization)
    return final_detections, ocr_grayscale
