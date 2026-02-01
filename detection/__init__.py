"""
Bib number detection module.

This module provides functions for detecting bib numbers in images using OCR.
It follows the same design philosophy as the preprocessing module: pure functions,
early validation, and clear separation of concerns.

Key components:
- bbox: Bounding box geometry utilities
- validation: Bib number validation and parsing
- regions: White region detection for candidate bibs
- filtering: Detection filtering (size, overlap)
- detector: Main detection orchestration
"""

from .detector import detect_bib_numbers
from .validation import is_valid_bib_number
from .regions import find_white_regions
from .bbox import bbox_area, bbox_iou, bbox_overlap_ratio, bbox_to_rect
from .filtering import filter_small_detections, filter_overlapping_detections

__all__ = [
    "detect_bib_numbers",
    "is_valid_bib_number",
    "find_white_regions",
    "bbox_area",
    "bbox_iou",
    "bbox_overlap_ratio",
    "bbox_to_rect",
    "filter_small_detections",
    "filter_overlapping_detections",
]
