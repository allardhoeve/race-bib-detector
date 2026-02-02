"""
Bib number detection module.

This module provides functions for detecting bib numbers in images using OCR.
It follows the same design philosophy as the preprocessing module: pure functions,
early validation, and clear separation of concerns.

Key components:
- types: Core data structures (Detection, PipelineResult, BibCandidate, Bbox)
- bbox: Bounding box geometry utilities
- validation: Bib number validation and parsing
- regions: White region detection for candidate bibs
- filtering: Detection filtering (size, overlap)
- detector: Main detection orchestration

The main entry point is `detect_bib_numbers()` which returns a `PipelineResult`
containing detections with full lineage tracking back to source candidates.
"""

from .types import Detection, PipelineResult, DetectionResult, BibCandidate, Bbox
from .detector import detect_bib_numbers, extract_bib_detections
from .validation import is_valid_bib_number
from .regions import find_bib_candidates, validate_detection_region
from .bbox import bbox_area, bbox_iou, bbox_overlap_ratio, bbox_to_rect, scale_bbox, scale_bboxes
from .filtering import filter_small_detections, filter_overlapping_detections

__all__ = [
    "Detection",
    "PipelineResult",
    "DetectionResult",  # Backward compatibility alias for PipelineResult
    "BibCandidate",
    "Bbox",
    "detect_bib_numbers",
    "extract_bib_detections",
    "is_valid_bib_number",
    "find_bib_candidates",
    "validate_detection_region",
    "bbox_area",
    "bbox_iou",
    "bbox_overlap_ratio",
    "bbox_to_rect",
    "scale_bbox",
    "scale_bboxes",
    "filter_small_detections",
    "filter_overlapping_detections",
]
