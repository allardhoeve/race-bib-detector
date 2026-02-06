"""
Data structures for face detections and embeddings.

These types are designed for both database storage (binary embeddings)
and JSON serialization (benchmarking artifacts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from geometry import Bbox

# Face bounding box: list of 4 [x, y] points (top-left, top-right, bottom-right, bottom-left)
FaceBbox = Bbox


@dataclass(frozen=True)
class FaceModelInfo:
    """Model metadata for face detection/embedding backends."""

    name: str
    version: str
    embedding_dim: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "embedding_dim": self.embedding_dim,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaceModelInfo":
        return cls(
            name=data["name"],
            version=data["version"],
            embedding_dim=int(data["embedding_dim"]),
        )


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Serialize a float32 embedding to raw bytes for SQLite storage."""
    if embedding.dtype != np.float32:
        embedding = embedding.astype(np.float32)
    return embedding.tobytes()


def embedding_from_bytes(data: bytes, dim: int) -> np.ndarray:
    """Deserialize raw bytes into a float32 embedding of the given dimension."""
    embedding = np.frombuffer(data, dtype=np.float32)
    if embedding.size != dim:
        raise ValueError(f"Embedding size mismatch: expected {dim}, got {embedding.size}")
    return embedding.copy()


@dataclass
class FaceDetection:
    """A face detection with optional embedding and artifact paths."""

    face_index: int
    bbox: FaceBbox
    embedding: np.ndarray | None
    model: FaceModelInfo
    snippet_path: str | None = None
    preview_path: str | None = None

    def to_dict(self, include_embedding: bool = True) -> dict[str, Any]:
        """Convert to dict suitable for JSON serialization."""
        return {
            "face_index": self.face_index,
            "bbox": self.bbox,
            "embedding": self.embedding.tolist() if include_embedding and self.embedding is not None else None,
            "model": self.model.to_dict(),
            "snippet_path": self.snippet_path,
            "preview_path": self.preview_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaceDetection":
        embedding = data.get("embedding")
        model_info = FaceModelInfo.from_dict(data["model"])
        embedding_array = None
        if embedding is not None:
            embedding_array = np.array(embedding, dtype=np.float32)
        return cls(
            face_index=int(data["face_index"]),
            bbox=data["bbox"],
            embedding=embedding_array,
            model=model_info,
            snippet_path=data.get("snippet_path"),
            preview_path=data.get("preview_path"),
        )


@dataclass(frozen=True)
class FaceCandidate:
    """A face candidate proposal with pass/fail metadata."""

    bbox: FaceBbox
    confidence: float | None
    passed: bool
    rejection_reason: str | None
    model: FaceModelInfo

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": self.bbox,
            "confidence": self.confidence,
            "passed": self.passed,
            "rejection_reason": self.rejection_reason,
            "model": self.model.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FaceCandidate":
        return cls(
            bbox=data["bbox"],
            confidence=data.get("confidence"),
            passed=bool(data["passed"]),
            rejection_reason=data.get("rejection_reason"),
            model=FaceModelInfo.from_dict(data["model"]),
        )
