"""
Face backend interface and local implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol

import cv2
import numpy as np

import config
from geometry import bbox_to_rect, rect_to_bbox
from .types import FaceBbox, FaceModelInfo

logger = logging.getLogger(__name__)


class FaceBackend(Protocol):
    """Interface for face detection + embedding backends."""

    def detect_faces(self, image: np.ndarray) -> list[FaceBbox]:
        """Detect faces in an RGB image and return bounding boxes."""

    def embed_faces(self, image: np.ndarray, boxes: list[FaceBbox]) -> list[np.ndarray]:
        """Compute embeddings for the given face boxes in an RGB image."""

    def model_info(self) -> FaceModelInfo:
        """Return model metadata (name, version, embedding dim)."""


def _normalize_embedding(vector: np.ndarray) -> np.ndarray:
    vector = vector.astype(np.float32)
    vector -= float(np.mean(vector))
    std = float(np.std(vector))
    if std > 1e-6:
        vector /= std
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return vector


@dataclass
class OpenCVHaarFaceBackend:
    """Local face backend using OpenCV's Haar cascade and pixel embeddings."""

    cascade_path: str = f"{cv2.data.haarcascades}haarcascade_frontalface_default.xml"

    def __post_init__(self) -> None:
        self._cascade = cv2.CascadeClassifier(self.cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade: {self.cascade_path}")

    def detect_faces(self, image: np.ndarray) -> list[FaceBbox]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face detection")
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=config.FACE_DETECTION_SCALE_FACTOR,
            minNeighbors=config.FACE_DETECTION_MIN_NEIGHBORS,
            minSize=config.FACE_DETECTION_MIN_SIZE,
        )
        return [rect_to_bbox(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def embed_faces(self, image: np.ndarray, boxes: list[FaceBbox]) -> list[np.ndarray]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face embedding")
        embeddings: list[np.ndarray] = []
        size = config.FACE_EMBEDDING_SIZE
        for bbox in boxes:
            x1, y1, x2, y2 = bbox_to_rect(bbox)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                embeddings.append(np.zeros(size * size, dtype=np.float32))
                continue
            crop = image[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            resized = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
            vector = resized.flatten().astype(np.float32)
            embeddings.append(_normalize_embedding(vector))
        return embeddings

    def model_info(self) -> FaceModelInfo:
        dim = config.FACE_EMBEDDING_SIZE * config.FACE_EMBEDDING_SIZE
        return FaceModelInfo(
            name="opencv_haar_pixels",
            version="1",
            embedding_dim=dim,
        )


_BACKENDS: dict[str, type[OpenCVHaarFaceBackend]] = {
    "opencv_haar": OpenCVHaarFaceBackend,
}


def get_face_backend() -> FaceBackend:
    """Instantiate the configured face backend."""
    backend_name = config.FACE_BACKEND
    backend_cls = _BACKENDS.get(backend_name)
    if backend_cls is None:
        raise ValueError(f"Unknown face backend: {backend_name}")
    return backend_cls()
