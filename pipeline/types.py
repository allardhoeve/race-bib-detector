"""Shared pipeline types for bib/face detection, linking, and scoring.

These types are used by both production (scan/pipeline.py) and benchmarking
(benchmarking/runner.py).  Extracted from benchmarking/ground_truth.py and
faces/autolink.py to eliminate the layering violation where production code
imported from the benchmarking package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from config import AUTOLINK_TORSO_BOTTOM, AUTOLINK_TORSO_HALF_WIDTH, AUTOLINK_TORSO_TOP
from geometry import Bbox, rect_to_bbox

# --- Tag sets ----------------------------------------------------------------

# Per-box bib scope (should this box be scored?)
BIB_BOX_SCOPES = frozenset({"bib", "not_bib", "bib_obscured", "bib_clipped"})
_BIB_BOX_UNSCORED = frozenset({"not_bib", "bib_obscured"})

# Per-box face scope (should this face be recognized?)
#   keep     — real participant face, scored during evaluation
#   exclude  — visible but irrelevant (spectators, crowd), excluded from scoring
#   uncertain — labeler unsure whether face matters, excluded until resolved
FACE_SCOPE_TAGS = frozenset({"keep", "exclude", "uncertain"})
_FACE_SCOPE_COMPAT = {"ignore": "exclude", "unknown": "uncertain"}

# Per-box face condition descriptors (short names, context is obvious)
FACE_BOX_TAGS = frozenset({"tiny", "blurry", "occluded", "profile", "looking_down"})


# =============================================================================
# Bib box
# =============================================================================


class BibBox(BaseModel):
    """A single bib bounding box with number and scope.

    Coordinates are in normalised [0, 1] image space.
    Legacy migrated boxes have x=y=w=h=0 (see ``has_coords``).
    """

    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"
    confidence: float | None = None  # OCR confidence (predictions only)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _migrate_tag_to_scope(cls, values: dict) -> dict:
        """Backward compat: very old format used 'tag' instead of 'scope'."""
        if isinstance(values, dict) and "scope" not in values and "tag" in values:
            values = dict(values)
            values["scope"] = values.pop("tag")
        return values

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        if v not in BIB_BOX_SCOPES:
            raise ValueError(f"Invalid bib box scope: {v!r}")
        return v

    @property
    def has_coords(self) -> bool:
        return self.w > 0 and self.h > 0


# =============================================================================
# Bib candidate trace (task-088)
# =============================================================================


class BibCandidateTrace(BaseModel):
    """Full trace of a single bib candidate through the pipeline.

    Records the candidate's journey: region detection → validation →
    OCR → acceptance.  Coordinates are normalised [0, 1] image space.
    """

    # Normalised bounding box
    x: float
    y: float
    w: float
    h: float

    # Region statistics (from BibCandidate)
    area: int
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float

    # Validation stage
    passed_validation: bool
    rejection_reason: str | None = None

    # OCR stage (best valid bib result, even if below threshold)
    ocr_text: str | None = None
    ocr_confidence: float | None = None

    # Acceptance stage
    accepted: bool = False
    bib_number: str | None = None

    def to_bib_box(self) -> BibBox:
        """Convert an accepted trace to a BibBox.

        Raises:
            ValueError: If this trace was not accepted.
        """
        if not self.accepted:
            raise ValueError("Cannot convert unaccepted trace to BibBox")
        return BibBox(
            x=self.x, y=self.y, w=self.w, h=self.h,
            number=self.bib_number or "",
            confidence=self.ocr_confidence,
        )


# =============================================================================
# Face candidate trace (task-089)
# =============================================================================


class FaceCandidateTrace(BaseModel):
    """Full trace of a single face candidate through the pipeline.

    Records the candidate's journey: detection → threshold → fallback chain →
    acceptance.  Coordinates are normalised [0, 1] image space.
    """

    # Normalised bounding box
    x: float
    y: float
    w: float
    h: float

    # Detection confidence (None for Haar backend)
    confidence: float | None = None

    # Backend threshold verdict
    passed: bool

    # Rejection reason (set when passed=False)
    rejection_reason: str | None = None

    # Final verdict after fallback chain (may promote passed=False → accepted=True)
    accepted: bool = False

    # Pixel-space bounding box (x1, y1, x2, y2) for embedding/artifact use
    pixel_bbox: tuple[int, int, int, int] | None = None

    # Future fields (task-090, 091)
    embedding: list[float] | None = None
    cluster_id: int | None = None
    cluster_distance: float | None = None
    nearest_other_distance: float | None = None

    def to_face_box(self) -> FaceBox:
        """Convert an accepted trace to a FaceBox.

        Raises:
            ValueError: If this trace was not accepted.
        """
        if not self.accepted:
            raise ValueError("Cannot convert unaccepted trace to FaceBox")
        return FaceBox(
            x=self.x, y=self.y, w=self.w, h=self.h,
            confidence=self.confidence,
        )

    def to_pixel_quad(self) -> Bbox:
        """Convert pixel_bbox (x1, y1, x2, y2) to a 4-point Bbox.

        Raises:
            ValueError: If pixel_bbox is not set.
        """
        if self.pixel_bbox is None:
            raise ValueError("pixel_bbox not set on this trace")
        x1, y1, x2, y2 = self.pixel_bbox
        return rect_to_bbox(x1, y1, x2 - x1, y2 - y1)


# =============================================================================
# Face box
# =============================================================================


class FaceBox(BaseModel):
    """A single face bounding box with scope and optional identity.

    Coordinates are in normalised [0, 1] image space.
    Coords are None for legacy boxes that pre-date coordinate recording.
    """

    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str = "keep"
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)
    cluster_id: int | None = None
    confidence: float | None = None  # detection confidence (predictions only)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _migrate_scope_compat(cls, values: dict) -> dict:
        """Remap legacy scope names before validation."""
        if isinstance(values, dict) and "scope" in values:
            values = dict(values)
            values["scope"] = _FACE_SCOPE_COMPAT.get(values["scope"], values["scope"])
        return values

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        if v not in FACE_SCOPE_TAGS:
            raise ValueError(f"Invalid face scope: {v!r}")
        return v

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        invalid = set(v) - FACE_BOX_TAGS
        if invalid:
            raise ValueError(f"Invalid face box tags: {invalid}")
        return v

    @property
    def has_coords(self) -> bool:
        return self.w is not None and self.w > 0


# =============================================================================
# Bib-face link
# =============================================================================


class BibFaceLink(BaseModel):
    """A directed association between a bib box and a face box in the same photo.

    Indices reference positions in ``BibPhotoLabel.boxes`` and
    ``FacePhotoLabel.boxes`` for the same content hash.

    Note: links become stale if boxes are reordered or deleted after linking.
    No automatic repair is done — re-label if the link list looks wrong.
    """

    bib_index: int    # index into BibPhotoLabel.boxes
    face_index: int   # index into FacePhotoLabel.boxes

    def to_pair(self) -> list[int]:
        return [self.bib_index, self.face_index]

    @classmethod
    def from_pair(cls, pair: list[int]) -> BibFaceLink:
        return cls(bib_index=pair[0], face_index=pair[1])


# =============================================================================
# Autolink predictor
# =============================================================================


@dataclass
class AutolinkResult:
    """Result of the autolink predictor for a single photo."""

    pairs: list[tuple[BibBox, FaceBox]] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)


def _torso_region(face_box: FaceBox) -> tuple[float, float, float, float]:
    """Return estimated torso bounding box (x, y, w, h) in normalised [0,1] coords.

    Uses empirically-derived multipliers from config (task-042).
    All offsets are in face-height units from face center.
    """
    fh = face_box.h
    cx = face_box.x + face_box.w / 2
    cy = face_box.y + fh / 2
    ty = cy + AUTOLINK_TORSO_TOP * fh
    th = (AUTOLINK_TORSO_BOTTOM - AUTOLINK_TORSO_TOP) * fh
    tw = 2 * AUTOLINK_TORSO_HALF_WIDTH * fh
    tx = cx - AUTOLINK_TORSO_HALF_WIDTH * fh
    return (tx, ty, tw, th)


def predict_links(
    bib_boxes: list[BibBox],
    face_boxes: list[FaceBox],
    bib_confidence_threshold: float = 0.5,
) -> AutolinkResult:
    """Rule-based autolink predictor for a single photo.

    Rules (applied in order):
    1. Single face rule: if exactly 1 face and exactly 1 high-confidence bib
       → link them unconditionally.
    2. Multi-face rule: for each face, find the nearest bib whose centroid
       falls inside the face's estimated torso region. One bib per face max.

    ``bib_confidence_threshold`` gates eligibility: all bibs are treated as
    having full confidence (1.0) because ``BibBox`` carries no confidence
    field. Passing a threshold ≥ 1.0 therefore suppresses all links, which
    is useful in tests.

    Args:
        bib_boxes: Detected bib boxes for this photo (normalised [0,1] coords).
        face_boxes: Detected face boxes for this photo (normalised [0,1] coords).
        bib_confidence_threshold: Minimum bib confidence required for autolink
            eligibility. All coordinate-bearing bibs are treated as confidence
            1.0; use a value > 1.0 to disable all links.

    Returns:
        AutolinkResult with ``pairs`` and ``provenance`` lists.
    """
    if not face_boxes or not bib_boxes:
        return AutolinkResult()

    if bib_confidence_threshold >= 1.0:
        return AutolinkResult()

    valid_faces = [f for f in face_boxes if f.has_coords]
    valid_bibs = [b for b in bib_boxes if b.has_coords]

    if not valid_faces or not valid_bibs:
        return AutolinkResult()

    # Rule 1: single face + single bib → link unconditionally.
    if len(valid_faces) == 1 and len(valid_bibs) == 1:
        return AutolinkResult(
            pairs=[(valid_bibs[0], valid_faces[0])],
            provenance=["single_face"],
        )

    # Rule 2: multi-face spatial matching.
    pairs: list[tuple[BibBox, FaceBox]] = []
    provenance: list[str] = []
    used_bibs: set[int] = set()

    for face in valid_faces:
        tx, ty, tw, th = _torso_region(face)
        face_cx = face.x + face.w / 2
        face_cy = face.y + face.h / 2

        candidates: list[tuple[float, int]] = []
        for bi, bib in enumerate(valid_bibs):
            if bi in used_bibs:
                continue
            bib_cx = bib.x + bib.w / 2
            bib_cy = bib.y + bib.h / 2
            if tx <= bib_cx <= tx + tw and ty <= bib_cy <= ty + th:
                dist = ((bib_cx - face_cx) ** 2 + (bib_cy - face_cy) ** 2) ** 0.5
                candidates.append((dist, bi))

        if candidates:
            candidates.sort()
            _, best_bi = candidates[0]
            pairs.append((valid_bibs[best_bi], face))
            provenance.append("single_face")
            used_bibs.add(best_bi)

    return AutolinkResult(pairs=pairs, provenance=provenance)
