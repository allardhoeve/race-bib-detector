"""
Face detection and embedding utilities.

This package provides a swappable backend interface, basic local backend(s),
and shared data structures for face detections and embeddings.
"""

from .backend import FaceBackend, get_face_backend, get_face_backend_by_name, OpenCVHaarFaceBackend
from .clustering import cluster_album_faces, similarity_label
from .types import FaceBbox, FaceModelInfo, FaceDetection, embedding_from_bytes, embedding_to_bytes

__all__ = [
    "FaceBackend",
    "get_face_backend",
    "get_face_backend_by_name",
    "OpenCVHaarFaceBackend",
    "FaceBbox",
    "FaceModelInfo",
    "FaceDetection",
    "embedding_from_bytes",
    "embedding_to_bytes",
    "cluster_album_faces",
    "similarity_label",
]
