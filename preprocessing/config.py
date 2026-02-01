"""
Configuration for the preprocessing pipeline.

All preprocessing steps are parameterized through PreprocessConfig to ensure
reproducibility and easy experimentation with different settings.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from config import TARGET_WIDTH, MIN_TARGET_WIDTH, MAX_TARGET_WIDTH


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
    """

    # Normalization settings
    target_width: Optional[int] = TARGET_WIDTH

    # Type normalization
    grayscale_dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint8))
    binary_dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint8))

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


@dataclass
class PreprocessResult:
    """Result of the preprocessing pipeline.

    Contains all intermediate and final images along with metadata needed
    to map detections back to original coordinates.

    Attributes:
        original: Original input image (RGB, uint8).
        grayscale: Grayscale version of the image.
        resized: Resized image (None if resizing was skipped).
        resized_grayscale: Resized grayscale image (None if resizing was skipped).
        scale_factor: Ratio of original width to resized width.
                     Used to map bounding boxes back to original coordinates.
        config: The configuration used for preprocessing.
    """

    original: np.ndarray
    grayscale: np.ndarray
    resized: Optional[np.ndarray]
    resized_grayscale: Optional[np.ndarray]
    scale_factor: float
    config: PreprocessConfig

    def map_to_original_coords(self, x: float, y: float) -> tuple[float, float]:
        """Map coordinates from resized image back to original image.

        Args:
            x: X coordinate in resized image.
            y: Y coordinate in resized image.

        Returns:
            Tuple of (x, y) coordinates in original image.
        """
        return (x * self.scale_factor, y * self.scale_factor)

    def map_bbox_to_original(self, bbox: list[list[float]]) -> list[list[float]]:
        """Map a bounding box from resized coordinates to original coordinates.

        Args:
            bbox: List of [x, y] points defining the bounding box.

        Returns:
            Bounding box with coordinates mapped to original image.
        """
        return [
            [p[0] * self.scale_factor, p[1] * self.scale_factor]
            for p in bbox
        ]
