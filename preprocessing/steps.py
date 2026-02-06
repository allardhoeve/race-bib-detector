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
    min_dynamic_range: float | None = None
    percentiles: tuple[float, float] = (5.0, 95.0)
    _applied: bool = field(default=False, init=False, repr=False)
    _observed_range: float | None = field(default=None, init=False, repr=False)
    _declined: bool = field(default=False, init=False, repr=False)

    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply CLAHE to a grayscale image."""
        if img.ndim != 2:
            raise ValueError(
                f"CLAHEStep requires grayscale input (2D array), "
                f"got {img.ndim}D array with shape {img.shape}"
            )
        if self.min_dynamic_range is not None:
            low, high = np.percentile(img, self.percentiles)
            dynamic_range = float(high - low)
            should_apply = dynamic_range < self.min_dynamic_range
            object.__setattr__(self, "_observed_range", dynamic_range)
            object.__setattr__(self, "_applied", should_apply)
            object.__setattr__(self, "_declined", not should_apply)
            if not should_apply:
                return img.copy()
        clahe = cv2.createCLAHE(
            clipLimit=self.clip_limit, tileGridSize=self.tile_size
        )
        result = clahe.apply(img)
        object.__setattr__(self, "_applied", True)
        object.__setattr__(self, "_declined", False)
        return result

    @property
    def name(self) -> str:
        return f"clahe(clip={self.clip_limit})"

    def get_metadata(self) -> dict[str, Any]:
        status = "applied" if self._applied else "declined"
        metadata = {
            "step_status": status,
            "skip_artifact": self._declined,
        }
        if self.min_dynamic_range is not None:
            metadata["step_metrics"] = {
                "dynamic_range": self._observed_range,
                "threshold": self.min_dynamic_range,
                "percentiles": self.percentiles,
            }
        return metadata


@dataclass
class StepResult:
    """Result of applying a single preprocessing step.

    Attributes:
        name: Name of the step that produced this result.
        image: Output image from the step.
        metadata: Any metadata produced by the step (e.g., scale_factor).
        artifact_path: Path where the image was saved (if artifact saving enabled).
    """

    name: str
    image: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None


@dataclass
class PipelineStepResults:
    """Results from running a preprocessing pipeline.

    Provides access to all intermediate images and aggregated metadata.

    Attributes:
        original: The original input image.
        steps: List of StepResult for each step in order.
        original_artifact_path: Path where original image was saved (if artifact saving enabled).
    """

    original: np.ndarray
    steps: list[StepResult] = field(default_factory=list)
    original_artifact_path: str | None = None
    step_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

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

    @property
    def artifact_paths(self) -> dict[str, str]:
        """Get all artifact paths as a dict mapping step name to path.

        Returns:
            Dict with keys like "original", "grayscale", etc. and path values.
            Only includes steps that have artifact_path set.
        """
        paths = {}
        if self.original_artifact_path:
            paths["original"] = self.original_artifact_path
        for step in self.steps:
            if step.artifact_path:
                # Normalize step name for use as key (e.g., "resize(1280)" -> "resize")
                key = step.name.split("(")[0]
                paths[key] = step.artifact_path
        return paths


def _save_image(img: np.ndarray, path: str) -> None:
    """Save an image to disk.

    Args:
        img: Image as numpy array (grayscale or BGR).
        path: Output file path.
    """
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, img)


@dataclass
class Pipeline:
    """A sequence of preprocessing steps to apply to images.

    The pipeline runs each step in order, passing the output of one step
    as the input to the next. All intermediate results are preserved.

    Attributes:
        steps: List of PreprocessStep instances to apply in order.
    """

    steps: list[PreprocessStep]

    def run(
        self,
        img: np.ndarray,
        artifact_dir: str | None = None,
    ) -> PipelineStepResults:
        """Run the pipeline on an image.

        Args:
            img: Input image as numpy array.
            artifact_dir: Optional directory to save intermediate images.
                         If provided, saves original.jpg and each step's output.

        Returns:
            PipelineStepResults containing all intermediate images and metadata.
        """
        result = PipelineStepResults(original=img.copy())
        current = img.copy()

        # Save original if artifact_dir provided
        if artifact_dir:
            original_path = f"{artifact_dir}/original.jpg"
            # Convert RGB to BGR for cv2 if color image
            if img.ndim == 3 and img.shape[2] == 3:
                _save_image(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), original_path)
            else:
                _save_image(img, original_path)
            result.original_artifact_path = original_path

        for step in self.steps:
            output = step.apply(current)
            metadata = step.get_metadata()
            step_key = step.name.split("(")[0]
            status = metadata.get("step_status", "applied")
            step_metrics = metadata.get("step_metrics", {})
            result.step_metadata[step_key] = {
                "status": status,
                "metrics": step_metrics,
            }

            # Save step output if artifact_dir provided
            artifact_path = None
            skip_artifact = bool(metadata.get("skip_artifact", False))
            if artifact_dir and not skip_artifact:
                # Use normalized step name for filename
                artifact_path = f"{artifact_dir}/{step_key}.jpg"
                _save_image(output, artifact_path)

            result.steps.append(
                StepResult(
                    name=step.name,
                    image=output,
                    metadata=metadata,
                    artifact_path=artifact_path,
                )
            )
            current = output

        return result

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)
