"""
Configuration for the preprocessing pipeline.

All preprocessing steps are parameterized through PreprocessConfig to ensure
reproducibility and easy experimentation with different settings.
"""

from dataclasses import dataclass, field
from typing import Optional, Any

import numpy as np

from config import (
    TARGET_WIDTH,
    MIN_TARGET_WIDTH,
    MAX_TARGET_WIDTH,
    CLAHE_ENABLED,
    CLAHE_CLIP_LIMIT,
    CLAHE_TILE_SIZE,
    CLAHE_DYNAMIC_RANGE_THRESHOLD,
    CLAHE_PERCENTILES,
)


@dataclass(frozen=True)
class PreprocessConfig:
    """Configuration for all preprocessing steps.

    This immutable configuration object parameterizes every step of the
    preprocessing pipeline. Default values are tuned for bib number detection
    in typical race photos.

    Attributes:
        target_width: Width to resize images to (preserving aspect ratio).
                     A fixed width ensures consistent kernel behavior.
                     Set to None to skip resizing.
        grayscale_dtype: Numpy dtype for grayscale images. Default is uint8
                        for compatibility with most CV operations.
        binary_dtype: Numpy dtype for binary (thresholded) images.
        clahe_enabled: Whether to use CLAHE contrast enhancement.
        clahe_clip_limit: Contrast limit for CLAHE.
        clahe_tile_size: Tile grid size for CLAHE.
        clahe_dynamic_range_threshold: Apply CLAHE only if p95-p5 is below this value.
        clahe_percentiles: Percentiles used for dynamic range estimation.
    """

    # Normalization settings
    target_width: Optional[int] = TARGET_WIDTH

    # Type normalization
    grayscale_dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint8))
    binary_dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint8))

    # CLAHE settings (contrast enhancement)
    clahe_enabled: bool = CLAHE_ENABLED
    clahe_clip_limit: float = CLAHE_CLIP_LIMIT
    clahe_tile_size: tuple[int, int] = CLAHE_TILE_SIZE
    clahe_dynamic_range_threshold: float = CLAHE_DYNAMIC_RANGE_THRESHOLD
    clahe_percentiles: tuple[float, float] = CLAHE_PERCENTILES

    def validate(self) -> None:
        """Validate configuration parameters.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if self.target_width is not None:
            if self.target_width <= 0:
                raise ValueError(f"target_width must be positive, got {self.target_width}")
            if self.target_width < MIN_TARGET_WIDTH:
                raise ValueError(
                    f"target_width={self.target_width} is too small for reliable OCR. "
                    f"Minimum recommended is {MIN_TARGET_WIDTH}, typical is 1024-1600."
                )
            if self.target_width > MAX_TARGET_WIDTH:
                raise ValueError(
                    f"target_width={self.target_width} is very large and may cause "
                    f"performance issues. Maximum recommended is {MAX_TARGET_WIDTH}."
                )

        # Validate dtypes are numpy-compatible
        try:
            np.dtype(self.grayscale_dtype)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid grayscale_dtype: {e}")

        try:
            np.dtype(self.binary_dtype)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid binary_dtype: {e}")

        if self.clahe_clip_limit <= 0:
            raise ValueError(
                f"clahe_clip_limit must be positive, got {self.clahe_clip_limit}"
            )

        if (
            not isinstance(self.clahe_tile_size, tuple)
            or len(self.clahe_tile_size) != 2
            or any(size <= 0 for size in self.clahe_tile_size)
        ):
            raise ValueError(
                "clahe_tile_size must be a tuple of two positive integers, "
                f"got {self.clahe_tile_size}"
            )

        if self.clahe_dynamic_range_threshold < 0:
            raise ValueError(
                "clahe_dynamic_range_threshold must be non-negative, "
                f"got {self.clahe_dynamic_range_threshold}"
            )

        low, high = self.clahe_percentiles
        if not (0.0 <= low < high <= 100.0):
            raise ValueError(
                "clahe_percentiles must be in ascending order within [0, 100], "
                f"got {self.clahe_percentiles}"
            )


@dataclass
class PreprocessResult:
    """Result of the preprocessing pipeline.

    Contains the original image and fully processed image ready for detection,
    along with metadata needed to map detections back to original coordinates.

    The pipeline is grayscale-first: all detection happens on the processed
    grayscale image. The original color image is preserved only for reference.

    Attributes:
        original: Original input image (RGB, uint8). Preserved for reference only.
        processed: Final processed image (grayscale, resized, enhanced).
                  This is the image used for all detection operations.
        scale_factor: Ratio of original width to processed width.
                     Used to map bounding boxes back to original coordinates.
        config: The configuration used for preprocessing.
        artifact_paths: Dict mapping step names to saved file paths (if artifact saving enabled).
        metadata: Aggregated metadata from all preprocessing steps.
    """

    original: np.ndarray
    processed: np.ndarray
    scale_factor: float
    config: PreprocessConfig
    artifact_paths: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def map_to_original_coords(self, x: float, y: float) -> tuple[float, float]:
        """Map coordinates from processed image back to original image.

        Args:
            x: X coordinate in processed image.
            y: Y coordinate in processed image.

        Returns:
            Tuple of (x, y) coordinates in original image.
        """
        return (x * self.scale_factor, y * self.scale_factor)

    def map_bbox_to_original(self, bbox: list[list[float]]) -> list[list[float]]:
        """Map a bounding box from processed coordinates to original coordinates.

        Args:
            bbox: List of [x, y] points defining the bounding box.

        Returns:
            Bounding box with coordinates mapped to original image.
        """
        return [
            [p[0] * self.scale_factor, p[1] * self.scale_factor]
            for p in bbox
        ]

    @property
    def ocr_image(self) -> np.ndarray:
        """Get the image to use for OCR and detection.

        This is an alias for `processed` for backwards compatibility.
        """
        return self.processed

    @property
    def ocr_grayscale(self) -> np.ndarray:
        """Get grayscale image at OCR resolution.

        This is an alias for `processed` for backwards compatibility.
        The processed image is always grayscale.
        """
        return self.processed

    @property
    def ocr_dimensions(self) -> tuple[int, int]:
        """Get (width, height) of the processed image."""
        h, w = self.processed.shape[:2]
        return w, h

    # Legacy property aliases for backwards compatibility
    @property
    def grayscale(self) -> np.ndarray:
        """Deprecated: Use `processed` instead."""
        return self.processed

    @property
    def resized(self) -> np.ndarray | None:
        """Deprecated: Use `processed` instead.

        Returns processed image (which is always resized if target_width is set).
        Returns None only if no processing was done (scale_factor == 1.0 and no enhancements).
        """
        if self.scale_factor != 1.0:
            return self.processed
        return None

    @property
    def resized_grayscale(self) -> np.ndarray | None:
        """Deprecated: Use `processed` instead."""
        return self.resized
