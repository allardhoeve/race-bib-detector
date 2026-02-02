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
class BibCandidate:
    """A candidate bib region (white rectangle) before OCR.

    Represents a potential bib area detected by white region analysis.
    Includes metadata about why the region was accepted or rejected,
    enabling debugging of the detection pipeline.

    Attributes:
        bbox: Region bounds as (x, y, w, h) in OCR coordinates
        area: Area of the region in pixels
        aspect_ratio: Width / height ratio
        median_brightness: Median pixel brightness (0-255)
        mean_brightness: Mean pixel brightness (0-255)
        relative_area: Area as fraction of total image area
        passed: Whether this candidate passed all filters
        rejection_reason: Why the candidate was rejected (None if passed)
    """

    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    area: int
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float
    passed: bool = True
    rejection_reason: str | None = None

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    def to_xywh(self) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) tuple."""
        return self.bbox

    def extract_region(self, image: np.ndarray) -> np.ndarray:
        """Extract this region from an image.

        Args:
            image: Image to extract from (grayscale or RGB)

        Returns:
            Cropped region as numpy array
        """
        x, y, w, h = self.bbox
        return image[y:y+h, x:x+w]

    @classmethod
    def create_rejected(
        cls,
        bbox: tuple[int, int, int, int],
        area: int,
        aspect_ratio: float,
        median_brightness: float,
        mean_brightness: float,
        relative_area: float,
        reason: str,
    ) -> "BibCandidate":
        """Create a rejected candidate with a reason."""
        return cls(
            bbox=bbox,
            area=area,
            aspect_ratio=aspect_ratio,
            median_brightness=median_brightness,
            mean_brightness=mean_brightness,
            relative_area=relative_area,
            passed=False,
            rejection_reason=reason,
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
