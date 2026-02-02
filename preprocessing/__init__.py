"""
Image preprocessing module for bib number detection.

This module provides pure, deterministic functions for preprocessing images
before OCR. All functions follow the pattern: input -> output with no mutation
of the original arrays.

Key components:
- config: PreprocessConfig dataclass for parameterizing all steps
- pipeline: run_pipeline() function that applies preprocessing steps in order
- steps: Class-based preprocessing steps with common PreprocessStep interface
- normalization: Image normalization functions (grayscale, resize)

Two APIs are available:
1. Function-based (legacy): run_pipeline(img, config) -> PreprocessResult
2. Class-based (new): Pipeline(steps=[...]).run(img) -> PipelineStepResults

The class-based API is recommended for custom pipelines and experimentation.
"""

from .config import PreprocessConfig, PreprocessResult
from .pipeline import run_pipeline, build_pipeline
from .normalization import to_grayscale, resize_to_width
from .steps import (
    PreprocessStep,
    GrayscaleStep,
    ResizeStep,
    CLAHEStep,
    Pipeline,
    PipelineStepResults,
    StepResult,
)

__all__ = [
    # Config and results
    "PreprocessConfig",
    "PreprocessResult",
    # Function API
    "run_pipeline",
    "build_pipeline",
    "to_grayscale",
    "resize_to_width",
    # Class-based API
    "PreprocessStep",
    "GrayscaleStep",
    "ResizeStep",
    "CLAHEStep",
    "Pipeline",
    "PipelineStepResults",
    "StepResult",
]
