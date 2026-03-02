"""Unified detection pipeline package.

Re-exports for backward compat and convenience.
"""

from pipeline.cluster import ClusterResult, cluster
from pipeline.single_photo import SinglePhotoResult, run_single_photo
from pipeline.types import (
    BibLabel,
    BibCandidateTrace,
    BibFaceLink,
    FaceCandidateTrace,
    FaceLabel,
    TraceLink,
    BIB_BOX_SCOPES,
    _BIB_BOX_UNSCORED,
    FACE_BOX_TAGS,
    FACE_SCOPE_TAGS,
    _FACE_SCOPE_COMPAT,
    predict_links,
)

__all__ = [
    "ClusterResult",
    "cluster",
    "SinglePhotoResult",
    "run_single_photo",
    "BibLabel",
    "BibCandidateTrace",
    "BibFaceLink",
    "FaceCandidateTrace",
    "FaceLabel",
    "TraceLink",
    "BIB_BOX_SCOPES",
    "_BIB_BOX_UNSCORED",
    "FACE_BOX_TAGS",
    "FACE_SCOPE_TAGS",
    "_FACE_SCOPE_COMPAT",
    "predict_links",
]
