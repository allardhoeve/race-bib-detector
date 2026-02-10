"""Face embedding interface and implementations.

Separate from detection — you may want DNN SSD for detection but
facenet-pytorch for embeddings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

import config
from .types import FaceBbox, FaceModelInfo
from geometry import bbox_to_rect

logger = logging.getLogger(__name__)


class FaceEmbedder(Protocol):
    """Interface for face embedding backends."""

    def embed(self, image: np.ndarray, boxes: list[FaceBbox]) -> list[np.ndarray]:
        """Compute embeddings for face crops in an RGB image.

        Args:
            image: RGB image as numpy array (H, W, 3).
            boxes: List of face bounding boxes (4-point polygon format).

        Returns:
            List of 1-D float32 embedding vectors, one per box.
        """

    def model_info(self) -> FaceModelInfo:
        """Return model metadata (name, version, embedding dim)."""


def _normalize_embedding(vector: np.ndarray) -> np.ndarray:
    """Mean-subtract, standardise, and L2-normalise an embedding vector."""
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
class PixelEmbedder:
    """Legacy pixel-based embedder: resize face crop to NxN grayscale."""

    size: int = config.FACE_EMBEDDING_SIZE

    def embed(self, image: np.ndarray, boxes: list[FaceBbox]) -> list[np.ndarray]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face embedding")
        embeddings: list[np.ndarray] = []
        for bbox in boxes:
            x1, y1, x2, y2 = bbox_to_rect(bbox)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                embeddings.append(np.zeros(self.size * self.size, dtype=np.float32))
                continue
            crop = image[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            resized = cv2.resize(gray, (self.size, self.size), interpolation=cv2.INTER_AREA)
            vector = resized.flatten().astype(np.float32)
            embeddings.append(_normalize_embedding(vector))
        return embeddings

    def model_info(self) -> FaceModelInfo:
        dim = self.size * self.size
        return FaceModelInfo(name="pixel", version="1", embedding_dim=dim)


@dataclass
class FaceNetEmbedder:
    """FaceNet (InceptionResNetV1) embedder via facenet-pytorch.

    Produces 512-dim L2-normalised embeddings pre-trained on VGGFace2.
    """

    _model: object = None  # lazy-loaded InceptionResnetV1

    def _get_model(self):
        if self._model is None:
            from facenet_pytorch import InceptionResnetV1
            self._model = InceptionResnetV1(pretrained="vggface2").eval()
        return self._model

    def embed(self, image: np.ndarray, boxes: list[FaceBbox]) -> list[np.ndarray]:
        if image.ndim != 3:
            raise ValueError("Expected RGB image for face embedding")
        import torch

        model = self._get_model()
        embeddings: list[np.ndarray] = []

        for bbox in boxes:
            x1, y1, x2, y2 = bbox_to_rect(bbox)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                embeddings.append(np.zeros(512, dtype=np.float32))
                continue

            crop = image[y1:y2, x1:x2]
            # Resize to 160x160 (InceptionResNetV1 input size)
            resized = cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA)
            # Convert to float tensor, normalize to [-1, 1]
            tensor = torch.from_numpy(resized).permute(2, 0, 1).float()
            tensor = (tensor - 127.5) / 128.0
            tensor = tensor.unsqueeze(0)  # batch dim

            with torch.no_grad():
                embedding = model(tensor).squeeze(0).cpu().numpy()

            # L2-normalise
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            embeddings.append(embedding.astype(np.float32))

        return embeddings

    def model_info(self) -> FaceModelInfo:
        return FaceModelInfo(name="facenet_vggface2", version="1", embedding_dim=512)


# --- Registry ----------------------------------------------------------------

_EMBEDDERS: dict[str, type] = {
    "pixel": PixelEmbedder,
    "facenet": FaceNetEmbedder,
}


def get_face_embedder() -> FaceEmbedder:
    """Instantiate the configured face embedder."""
    return get_face_embedder_by_name(config.FACE_EMBEDDER)


def get_face_embedder_by_name(name: str) -> FaceEmbedder:
    """Instantiate a face embedder by name."""
    cls = _EMBEDDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown face embedder: {name}")
    return cls()
