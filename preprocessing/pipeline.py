"""
Preprocessing pipeline that applies all steps in order.

The pipeline is the main entry point for preprocessing images. It applies
normalization steps based on the provided configuration and returns all
intermediate results for debugging and visualization.

This module provides two APIs:
1. run_pipeline() - Function API that builds and runs a standard pipeline
2. Pipeline class - Class-based API for composable step sequences

The run_pipeline() function internally uses the Pipeline class.

Pipeline Philosophy:
- All detection happens on grayscale images
- The pipeline is: Grayscale → (CLAHE if needed) → Resize
- Original color image is preserved only for reference
"""

import numpy as np

from .config import PreprocessConfig, PreprocessResult
from .steps import (
    Pipeline,
    GrayscaleStep,
    ResizeStep,
    PreprocessStep,
    CLAHEStep,
)


def _validate_input(img: np.ndarray) -> None:
    """Validate input image array.

    Raises:
        TypeError: If img is not a numpy array.
        ValueError: If img has invalid dimensions or is empty.
    """
    if not isinstance(img, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray, got {type(img).__name__}")

    if img.ndim < 2 or img.ndim > 3:
        raise ValueError(
            f"Image must be 2D or 3D array, got {img.ndim}D array with shape {img.shape}"
        )

    if img.size == 0:
        raise ValueError("Image array is empty")


def build_pipeline(config: PreprocessConfig) -> Pipeline:
    """Build a Pipeline from a PreprocessConfig.

    Creates the standard grayscale-first preprocessing pipeline:
    1. GrayscaleStep - Convert to grayscale
    2. CLAHEStep - Optional contrast enhancement (conditional)
    3. ResizeStep - Resize to target width (if configured)

    Args:
        config: Preprocessing configuration.

    Returns:
        Pipeline configured according to the config.
    """
    steps: list[PreprocessStep] = []

    # Step 1: Always convert to grayscale first
    steps.append(GrayscaleStep(dtype=config.grayscale_dtype))

    # Step 2: CLAHE contrast enhancement (conditional)
    if config.clahe_enabled:
        steps.append(
            CLAHEStep(
                clip_limit=config.clahe_clip_limit,
                tile_size=config.clahe_tile_size,
                min_dynamic_range=config.clahe_dynamic_range_threshold,
                percentiles=config.clahe_percentiles,
            )
        )

    # Step 3: Resize if configured
    if config.target_width is not None:
        steps.append(ResizeStep(target_width=config.target_width))

    return Pipeline(steps=steps)


def run_pipeline(
    img: np.ndarray,
    config: PreprocessConfig | None = None,
    artifact_dir: str | None = None,
) -> PreprocessResult:
    """Apply the full preprocessing pipeline to an image.

    This function applies all preprocessing steps in order:
    1. Convert to grayscale
    2. Optional CLAHE (contrast enhancement)
    3. Resize to target width (if configured)

    All operations are pure and non-mutating. The original image is preserved.

    Args:
        img: Input image as numpy array. Expected to be RGB with shape (H, W, 3)
             and dtype uint8, but other formats are handled gracefully.
        config: Preprocessing configuration. If None, uses default settings.
        artifact_dir: Optional directory to save intermediate images.
                     If provided, saves original.jpg and each step's output.

    Returns:
        PreprocessResult containing original and processed images with metadata.

    Raises:
        ValueError: If configuration is invalid or image cannot be processed.
        TypeError: If inputs are of wrong type.

    Examples:
        >>> img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        >>> result = run_pipeline(img)
        >>> result.processed.shape  # Grayscale, resized
        (640, 1280)
        >>> result.scale_factor
        1.5625
    """
    if config is None:
        config = PreprocessConfig()

    # Validate configuration
    config.validate()

    # Validate input
    _validate_input(img)

    # Store original (make a copy to ensure immutability)
    original = img.copy()

    # Build and run the pipeline
    pipeline = build_pipeline(config)
    pipeline_result = pipeline.run(original, artifact_dir=artifact_dir)

    # Extract scale factor from pipeline metadata
    scale_factor = pipeline_result.scale_factor

    return PreprocessResult(
        original=original,
        processed=pipeline_result.final,
        scale_factor=scale_factor,
        config=config,
        artifact_paths=pipeline_result.artifact_paths,
    )
