"""
Preprocessing pipeline that applies all steps in order.

The pipeline is the main entry point for preprocessing images. It applies
normalization steps based on the provided configuration and returns all
intermediate results for debugging and visualization.
"""

import numpy as np

from .config import PreprocessConfig, PreprocessResult
from .normalization import to_grayscale, resize_to_width


def run_pipeline(
    img: np.ndarray,
    config: PreprocessConfig | None = None,
) -> PreprocessResult:
    """Apply the full preprocessing pipeline to an image.

    This function applies all preprocessing steps in order:
    1. Convert to grayscale
    2. Resize to target width (if configured)

    All operations are pure and non-mutating. The original image is preserved.

    Args:
        img: Input image as numpy array. Expected to be RGB with shape (H, W, 3)
             and dtype uint8, but other formats are handled gracefully.
        config: Preprocessing configuration. If None, uses default settings.

    Returns:
        PreprocessResult containing all intermediate images and metadata.

    Raises:
        ValueError: If configuration is invalid or image cannot be processed.
        TypeError: If inputs are of wrong type.

    Examples:
        >>> img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        >>> result = run_pipeline(img)
        >>> result.grayscale.shape
        (1000, 2000)
        >>> result.resized.shape
        (640, 1280, 3)
        >>> result.scale_factor
        1.5625
    """
    if config is None:
        config = PreprocessConfig()

    # Validate configuration
    config.validate()

    # Validate input
    if not isinstance(img, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray, got {type(img).__name__}")

    if img.ndim < 2 or img.ndim > 3:
        raise ValueError(
            f"Image must be 2D or 3D array, got {img.ndim}D array with shape {img.shape}"
        )

    if img.size == 0:
        raise ValueError("Image array is empty")

    # Store original (make a copy to ensure immutability)
    original = img.copy()

    # Step 1: Convert to grayscale
    grayscale = to_grayscale(original, dtype=config.grayscale_dtype)

    # Step 2: Resize if configured
    resized = None
    resized_grayscale = None
    scale_factor = 1.0

    if config.target_width is not None:
        resized, scale_factor = resize_to_width(original, config.target_width)
        resized_grayscale = to_grayscale(resized, dtype=config.grayscale_dtype)

    return PreprocessResult(
        original=original,
        grayscale=grayscale,
        resized=resized,
        resized_grayscale=resized_grayscale,
        scale_factor=scale_factor,
        config=config,
    )
