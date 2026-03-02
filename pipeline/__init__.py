"""Unified detection pipeline package.

Re-exports for backward compat and convenience.
"""

from pipeline.single_photo import SinglePhotoResult, run_single_photo
from pipeline.types import (
    AutolinkResult,
    BibBox,
    BibCandidateTrace,
    BibFaceLink,
    FaceCandidateTrace,
    FaceBox,
    BIB_BOX_SCOPES,
    _BIB_BOX_UNSCORED,
    FACE_BOX_TAGS,
    FACE_SCOPE_TAGS,
    _FACE_SCOPE_COMPAT,
    predict_links,
)

__all__ = [
    "SinglePhotoResult",
    "run_single_photo",
    "AutolinkResult",
    "BibBox",
    "BibCandidateTrace",
    "BibFaceLink",
    "FaceCandidateTrace",
    "FaceBox",
    "BIB_BOX_SCOPES",
    "_BIB_BOX_UNSCORED",
    "FACE_BOX_TAGS",
    "FACE_SCOPE_TAGS",
    "_FACE_SCOPE_COMPAT",
    "predict_links",
]
