"""
Type definitions for the detection module.

This module defines the core data structures used throughout the detection pipeline.
"""

from dataclasses import dataclass

import numpy as np


# Type alias for a bounding box: list of 4 [x, y] coordinate pairs (quadrilateral)
Bbox = list[list[int]]


@dataclass
class Detection:
    """A detected bib number with its location and confidence.

    Attributes:
        bib_number: The detected bib number as a string (e.g., "123", "42")
        confidence: OCR confidence score between 0 and 1
        bbox: Bounding box as list of 4 [x, y] points defining a quadrilateral
    """

    bib_number: str
    confidence: float
    bbox: Bbox

    def scale_bbox(self, factor: float) -> "Detection":
        """Return a new Detection with scaled bounding box coordinates.

        Args:
            factor: Scale factor to apply to all coordinates

        Returns:
            New Detection with scaled bbox (coordinates as integers)
        """
        scaled_bbox = [[int(p[0] * factor), int(p[1] * factor)] for p in self.bbox]
        return Detection(
            bib_number=self.bib_number,
            confidence=self.confidence,
            bbox=scaled_bbox,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation (for backwards compatibility).

        Returns:
            Dict with 'bib_number', 'confidence', 'bbox' keys
        """
        return {
            "bib_number": self.bib_number,
            "confidence": self.confidence,
            "bbox": self.bbox,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Detection":
        """Create Detection from dictionary.

        Args:
            d: Dict with 'bib_number', 'confidence', 'bbox' keys

        Returns:
            Detection instance
        """
        return cls(
            bib_number=d["bib_number"],
            confidence=d["confidence"],
            bbox=d["bbox"],
        )


@dataclass
class DetectionResult:
    """Result of the bib number detection pipeline.

    Bundles all outputs from detect_bib_numbers() including metadata needed
    for coordinate mapping and visualization.

    Attributes:
        detections: List of detected bib numbers (in original image coordinates)
        ocr_grayscale: Grayscale image used for OCR (at OCR resolution)
        original_dimensions: (width, height) of the original input image
        ocr_dimensions: (width, height) of the image used for OCR
        scale_factor: Ratio to map OCR coords back to original (original_width / ocr_width)
    """

    detections: list[Detection]
    ocr_grayscale: np.ndarray
    original_dimensions: tuple[int, int]  # (width, height)
    ocr_dimensions: tuple[int, int]  # (width, height)
    scale_factor: float

    @property
    def ocr_scale(self) -> float:
        """Scale factor to map original coords to OCR coords (inverse of scale_factor)."""
        return 1.0 / self.scale_factor if self.scale_factor != 0 else 1.0

    def detections_at_ocr_scale(self) -> list[Detection]:
        """Return detections with bboxes scaled to OCR image coordinates.

        Useful for visualization on the OCR grayscale image.
        """
        return [det.scale_bbox(self.ocr_scale) for det in self.detections]
