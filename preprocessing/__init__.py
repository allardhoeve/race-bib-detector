"""
Image preprocessing module for bib number detection.

This module provides pure, deterministic functions for preprocessing images
before OCR. All functions follow the pattern: input -> output with no mutation
of the original arrays.

Key components:
- config: PreprocessConfig dataclass for parameterizing all steps
- pipeline: run_pipeline() function that applies preprocessing steps in order
- normalization: Image normalization functions (grayscale, resize)
"""

from .config import PreprocessConfig, PreprocessResult
from .pipeline import run_pipeline
from .normalization import to_grayscale, resize_to_width

__all__ = [
    "PreprocessConfig",
    "PreprocessResult",
    "run_pipeline",
    "to_grayscale",
    "resize_to_width",
]
