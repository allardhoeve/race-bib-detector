"""
Face backend interface and local implementations.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

import config
from geometry import bbox_to_rect, rect_to_bbox
from .types import FaceBbox, FaceCandidate, FaceModelInfo

logger = logging.getLogger(__name__)


class FaceBackend(Protocol):
    """Interface for face detection backends."""

    def detect_faces(self, image: np.ndarray) -> list[FaceBbox]:
        """Detect faces in an RGB image and return bounding boxes."""

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        """Detect face candidates (including rejected ones) for an RGB image."""


@dataclass
class OpenCVHaarFaceBackend:
    """Local face backend using OpenCV's Haar cascade."""

    cascade_path: str = f"{cv2.data.haarcascades}haarcascade_frontalface_default.xml"
    min_neighbors: int | None = None
    scale_factor: float | None = None
    min_size: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if self.min_neighbors is None:
            self.min_neighbors = config.FACE_DETECTION_MIN_NEIGHBORS
        if self.scale_factor is None:
            self.scale_factor = config.FACE_DETECTION_SCALE_FACTOR
        if self.min_size is None:
            self.min_size = config.FACE_DETECTION_MIN_SIZE
        self._cascade = cv2.CascadeClassifier(self.cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade: {self.cascade_path}")
        eye_cascade_path = f"{cv2.data.haarcascades}{config.FACE_DETECTION_EYE_CASCADE}"
        self._eye_cascade = cv2.CascadeClassifier(eye_cascade_path)
        if self._eye_cascade.empty():
            raise RuntimeError(f"Failed to load eye Haar cascade: {eye_cascade_path}")

    def detect_faces(self, image: np.ndarray) -> list[FaceBbox]:
        candidates = self.detect_face_candidates(image)
        return [candidate.bbox for candidate in candidates if candidate.passed]

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face detection")
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.min_neighbors,
            minSize=self.min_size,
        )
        model_info = self.model_info()
        boxes = [rect_to_bbox(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]
        if config.FACE_DETECTION_REQUIRE_EYES <= 0:
            return [
                FaceCandidate(
                    bbox=bbox,
                    confidence=None,
                    passed=True,
                    rejection_reason=None,
                    model=model_info,
                )
                for bbox in boxes
            ]
        candidates: list[FaceCandidate] = []
        for bbox in boxes:
            x1, y1, x2, y2 = bbox_to_rect(bbox)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(gray.shape[1], x2)
            y2 = min(gray.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = gray[y1:y2, x1:x2]
            eyes = self._eye_cascade.detectMultiScale(
                crop,
                scaleFactor=1.1,
                minNeighbors=config.FACE_DETECTION_EYE_MIN_NEIGHBORS,
                minSize=config.FACE_DETECTION_EYE_MIN_SIZE,
            )
            passed = len(eyes) >= config.FACE_DETECTION_REQUIRE_EYES
            candidates.append(
                FaceCandidate(
                    bbox=bbox,
                    confidence=None,
                    passed=passed,
                    rejection_reason=None if passed else "eyes",
                    model=model_info,
                )
            )
        return candidates

    def model_info(self) -> FaceModelInfo:
        return FaceModelInfo(name="opencv_haar", version="1", embedding_dim=0)


@dataclass
class OpenCVDnnSsdFaceBackend:
    """Local face backend using OpenCV DNN SSD."""

    proto_path: str = config.FACE_DNN_PROTO_PATH
    model_path: str = config.FACE_DNN_MODEL_PATH
    confidence_min: float | None = None
    nms_iou: float | None = None
    fallback_confidence_min: float | None = None

    def __post_init__(self) -> None:
        if self.confidence_min is None:
            self.confidence_min = config.FACE_DNN_CONFIDENCE_MIN
        if self.nms_iou is None:
            self.nms_iou = config.FACE_DNN_NMS_IOU
        if self.fallback_confidence_min is None:
            self.fallback_confidence_min = config.FACE_DNN_FALLBACK_CONFIDENCE_MIN
        proto_path = Path(self.proto_path)
        model_path = Path(self.model_path)
        if not proto_path.exists():
            raise RuntimeError(
                "Missing DNN prototxt file. Set FACE_DNN_PROTO_PATH to the local model path."
            )
        if not model_path.exists():
            raise RuntimeError(
                "Missing DNN model file. Set FACE_DNN_MODEL_PATH to the local model path."
            )
        self._net = cv2.dnn.readNetFromCaffe(str(proto_path), str(model_path))

    def detect_faces(self, image: np.ndarray) -> list[FaceBbox]:
        candidates = self.detect_face_candidates(image)
        return [candidate.bbox for candidate in candidates if candidate.passed]

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face detection")
        height, width = image.shape[:2]
        blob = cv2.dnn.blobFromImage(
            image,
            scalefactor=config.FACE_DNN_SCALE,
            size=config.FACE_DNN_INPUT_SIZE,
            mean=config.FACE_DNN_MEAN,
            swapRB=config.FACE_DNN_SWAP_RB,
            crop=False,
        )
        self._net.setInput(blob)
        detections = self._net.forward()

        model_info = self.model_info()
        boxes: list[list[int]] = []
        confidences: list[float] = []
        candidates: list[FaceCandidate] = []
        for idx in range(detections.shape[2]):
            confidence = float(detections[0, 0, idx, 2])
            box = detections[0, 0, idx, 3:7] * np.array([width, height, width, height])
            x1, y1, x2, y2 = box.astype(int)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(width, x2)
            y2 = min(height, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            bbox = rect_to_bbox(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            passed = confidence >= self.confidence_min
            candidates.append(
                FaceCandidate(
                    bbox=bbox,
                    confidence=confidence,
                    passed=passed,
                    rejection_reason=None if passed else "confidence",
                    model=model_info,
                )
            )
            if passed:
                boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
                confidences.append(confidence)

        if not boxes:
            return candidates

        indices = cv2.dnn.NMSBoxes(
            boxes,
            confidences,
            score_threshold=self.confidence_min,
            nms_threshold=self.nms_iou,
        )
        kept: set[int] = set()
        for idx in indices:
            i = int(idx[0]) if isinstance(idx, (list, tuple, np.ndarray)) else int(idx)
            kept.add(i)

        # Reconcile candidates with NMS-kept indices.
        passed_candidates: list[FaceCandidate] = []
        passed_index = 0
        for candidate in candidates:
            if not candidate.passed:
                passed_candidates.append(candidate)
                continue
            if passed_index in kept:
                passed_candidates.append(candidate)
            else:
                passed_candidates.append(
                    FaceCandidate(
                        bbox=candidate.bbox,
                        confidence=candidate.confidence,
                        passed=False,
                        rejection_reason="nms",
                        model=candidate.model,
                    )
                )
            passed_index += 1
        return passed_candidates

    def model_info(self) -> FaceModelInfo:
        return FaceModelInfo(name="opencv_dnn_ssd", version="1", embedding_dim=0)


_BACKENDS: dict[str, type] = {
    "opencv_haar": OpenCVHaarFaceBackend,
    "opencv_dnn_ssd": OpenCVDnnSsdFaceBackend,
}


def get_face_backend() -> FaceBackend:
    """Instantiate the configured face backend."""
    return get_face_backend_by_name(config.FACE_BACKEND)


def get_face_backend_by_name(backend_name: str) -> FaceBackend:
    """Instantiate a face backend by name."""
    backend_cls = _BACKENDS.get(backend_name)
    if backend_cls is None:
        raise ValueError(f"Unknown face backend: {backend_name}")
    return backend_cls()


def get_face_backend_with_overrides(
    backend_name: str | None = None,
    **kwargs,
) -> FaceBackend:
    """Instantiate a face backend with parameter overrides.

    Args:
        backend_name: Backend name (e.g. ``"opencv_dnn_ssd"``). Defaults to
            ``config.FACE_BACKEND`` if None.
        **kwargs: Constructor keyword arguments to override. Must be valid
            field names for the selected backend class.

    Raises:
        ValueError: If ``backend_name`` is unknown or any kwarg is not a
            valid field for the selected backend.
    """
    name = backend_name if backend_name is not None else config.FACE_BACKEND
    backend_cls = _BACKENDS.get(name)
    if backend_cls is None:
        raise ValueError(f"Unknown face backend: {name!r}")
    valid_fields = {f.name for f in dataclasses.fields(backend_cls)}
    unknown = set(kwargs) - valid_fields
    if unknown:
        raise ValueError(
            f"Unknown kwargs for backend {name!r}: {sorted(unknown)}"
        )
    return backend_cls(**kwargs)
