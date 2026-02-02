"""
Preprocessing step classes with a common interface.

Each step is a frozen dataclass that implements the PreprocessStep interface.
Steps are pure: they take an input and return a new output without mutating
the original array.

Usage:
    from preprocessing.steps import GrayscaleStep, ResizeStep, Pipeline

    pipeline = Pipeline(steps=[
        GrayscaleStep(),
        ResizeStep(target_width=1280),
    ])
    result = pipeline.run(image)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .normalization import to_grayscale, resize_to_width


class PreprocessStep(ABC):
    """Base class for preprocessing steps.

    All preprocessing steps must implement this interface. Steps should be
    pure functions: they take an input image and return a new output without
    mutating the original.

    Steps can optionally produce metadata (like scale factors) that needs to
    be preserved for later coordinate mapping.
    """

    @abstractmethod
    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply this preprocessing step to an image.

        Must be pure: never mutates the input image.

        Args:
            img: Input image as numpy array.

        Returns:
            Processed image as a new numpy array.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging and debugging."""
        pass

    def get_metadata(self) -> dict[str, Any]:
        """Return any metadata produced by this step.

        Override this method if your step produces metadata that needs
        to be preserved (e.g., scale factors for coordinate mapping).

        Returns:
            Dictionary of metadata. Empty by default.
        """
        return {}


@dataclass(frozen=True)
class GrayscaleStep(PreprocessStep):
    """Convert image to grayscale.

    Handles RGB, RGBA, and already-grayscale images.

    Attributes:
        dtype: Output numpy dtype. Default is uint8 for CV2 compatibility.
    """

    dtype: np.dtype = field(default_factory=lambda: np.dtype(np.uint8))

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Convert image to grayscale."""
        return to_grayscale(img, self.dtype)

    @property
    def name(self) -> str:
        return "grayscale"


@dataclass
class ResizeStep(PreprocessStep):
    """Resize image to a target width, preserving aspect ratio.

    This step tracks the scale factor as metadata for later coordinate
    mapping back to the original image.

    Attributes:
        target_width: Desired width in pixels.
        interpolation: OpenCV interpolation method for downscaling.
                      Default is INTER_AREA which is best for downscaling.
    """

    target_width: int
    interpolation: int = cv2.INTER_AREA
    _scale_factor: float = field(default=1.0, init=False, repr=False)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Resize image to target width."""
        resized, scale_factor = resize_to_width(
            img, self.target_width, self.interpolation
        )
        # Store scale factor for metadata retrieval
        # Note: We use object.__setattr__ because the instance isn't frozen
        object.__setattr__(self, "_scale_factor", scale_factor)
        return resized

    @property
    def name(self) -> str:
        return f"resize({self.target_width})"

    def get_metadata(self) -> dict[str, Any]:
        """Return scale factor for coordinate mapping."""
        return {"scale_factor": self._scale_factor}


@dataclass(frozen=True)
class CLAHEStep(PreprocessStep):
    """Apply Contrast Limited Adaptive Histogram Equalization.

    CLAHE normalizes brightness across the image, making it easier to
    detect bibs that appear gray/off-white due to lighting conditions.

    Requires grayscale input.

    Attributes:
        clip_limit: Threshold for contrast limiting. Higher values give
                   more contrast but may amplify noise. Default is 2.0.
        tile_size: Size of grid for histogram equalization. Smaller tiles
                  give more local adaptation. Default is (8, 8).
    """

    clip_limit: float = 2.0
    tile_size: tuple[int, int] = (8, 8)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply CLAHE to a grayscale image."""
        if img.ndim != 2:
            raise ValueError(
                f"CLAHEStep requires grayscale input (2D array), "
                f"got {img.ndim}D array with shape {img.shape}"
            )
        clahe = cv2.createCLAHE(
            clipLimit=self.clip_limit, tileGridSize=self.tile_size
        )
        return clahe.apply(img)

    @property
    def name(self) -> str:
        return f"clahe(clip={self.clip_limit})"


@dataclass
class StepResult:
    """Result of applying a single preprocessing step.

    Attributes:
        name: Name of the step that produced this result.
        image: Output image from the step.
        metadata: Any metadata produced by the step (e.g., scale_factor).
    """

    name: str
    image: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineStepResults:
    """Results from running a preprocessing pipeline.

    Provides access to all intermediate images and aggregated metadata.

    Attributes:
        original: The original input image.
        steps: List of StepResult for each step in order.
    """

    original: np.ndarray
    steps: list[StepResult] = field(default_factory=list)

    @property
    def final(self) -> np.ndarray:
        """Get the final processed image."""
        if not self.steps:
            return self.original
        return self.steps[-1].image

    def get_intermediate(self, step_name: str) -> np.ndarray | None:
        """Get intermediate image by step name.

        Args:
            step_name: Name of the step (e.g., "grayscale", "resize(1280)").

        Returns:
            The image produced by that step, or None if not found.
        """
        for step in self.steps:
            if step.name == step_name:
                return step.image
        return None

    def get_metadata(self, key: str) -> Any | None:
        """Get metadata value from any step.

        Searches steps in order and returns the first match.

        Args:
            key: Metadata key to look for (e.g., "scale_factor").

        Returns:
            The metadata value, or None if not found.
        """
        for step in self.steps:
            if key in step.metadata:
                return step.metadata[key]
        return None

    @property
    def scale_factor(self) -> float:
        """Convenience property for the common scale_factor metadata."""
        return self.get_metadata("scale_factor") or 1.0

    @property
    def all_metadata(self) -> dict[str, Any]:
        """Get all metadata from all steps, merged into one dict.

        Later steps override earlier ones if keys conflict.
        """
        result = {}
        for step in self.steps:
            result.update(step.metadata)
        return result


@dataclass
class Pipeline:
    """A sequence of preprocessing steps to apply to images.

    The pipeline runs each step in order, passing the output of one step
    as the input to the next. All intermediate results are preserved.

    Attributes:
        steps: List of PreprocessStep instances to apply in order.
    """

    steps: list[PreprocessStep]

    def run(self, img: np.ndarray) -> PipelineStepResults:
        """Run the pipeline on an image.

        Args:
            img: Input image as numpy array.

        Returns:
            PipelineStepResults containing all intermediate images and metadata.
        """
        result = PipelineStepResults(original=img.copy())
        current = img.copy()

        for step in self.steps:
            output = step.apply(current)
            metadata = step.get_metadata()
            result.steps.append(
                StepResult(name=step.name, image=output, metadata=metadata)
            )
            current = output

        return result

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)
