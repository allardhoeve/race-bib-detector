"""Ghost labeling — precomputed detection suggestions for the labeling UI.

Runs bib and face detection on benchmark photos and stores the results
as *suggestions* in a separate file (``suggestions.json``).  These are
shown as dashed outlines in the labeling UI; the user can accept, adjust,
or ignore them.

Suggestions are **not** ground truth — they live alongside GT but are
never mixed in.  Each suggestion carries provenance metadata so the UI
can show which backend produced it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Geometry helper
# =============================================================================


def normalize_quad(
    quad: list[list[int]],
    img_width: int,
    img_height: int,
) -> tuple[float, float, float, float]:
    """Convert a pixel-space quadrilateral to normalised (x, y, w, h).

    Takes the axis-aligned bounding rectangle of the quad, then divides
    by image dimensions to get coordinates in [0, 1] space.

    Args:
        quad: Four [x, y] points defining the quadrilateral.
        img_width: Image width in pixels.
        img_height: Image height in pixels.

    Returns:
        (x, y, w, h) in normalised [0, 1] space.  Returns (0, 0, 0, 0)
        if image dimensions are zero.
    """
    if img_width <= 0 or img_height <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x1, y1 = min(xs), min(ys)
    x2, y2 = max(xs), max(ys)

    return (
        x1 / img_width,
        y1 / img_height,
        (x2 - x1) / img_width,
        (y2 - y1) / img_height,
    )


# =============================================================================
# Data structures
# =============================================================================


class Provenance(BaseModel):
    """Metadata about which backend/version produced a suggestion.

    Attributes:
        backend: Detection backend name (e.g. ``"easyocr"``, ``"opencv_dnn_ssd"``).
        version: Backend or package version string.
        config: Key config values that affect output.
    """

    backend: str
    version: str
    config: dict = {}

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> Provenance:
        return cls.model_validate(data)


class BibSuggestion(BaseModel):
    """A suggested bib bounding box with detected number.

    Coordinates are in normalised [0, 1] image space.
    """

    x: float
    y: float
    w: float
    h: float
    number: str
    confidence: float

    @property
    def has_coords(self) -> bool:
        return self.w > 0 and self.h > 0

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> BibSuggestion:
        return cls.model_validate(data)


class FaceSuggestion(BaseModel):
    """A suggested face bounding box.

    Coordinates are in normalised [0, 1] image space.
    """

    x: float
    y: float
    w: float
    h: float
    confidence: float

    @property
    def has_coords(self) -> bool:
        return self.w > 0 and self.h > 0

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> FaceSuggestion:
        return cls.model_validate(data)


class PhotoSuggestions(BaseModel):
    """All suggestions for a single photo.

    Attributes:
        content_hash: Photo identity.
        bibs: Suggested bib bounding boxes.
        faces: Suggested face bounding boxes.
        provenance: Which backend/version produced these suggestions.
    """

    content_hash: str
    bibs: list[BibSuggestion] = []
    faces: list[FaceSuggestion] = []
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        # content_hash is the JSON key, not stored in the value dict.
        # exclude_none drops provenance when absent.
        return self.model_dump(exclude={"content_hash"}, exclude_none=True)

    @classmethod
    def from_dict(cls, content_hash: str, data: dict) -> PhotoSuggestions:
        """Load from a value dict, with content_hash passed separately.

        The JSON file stores content_hash as the dict key, not inside the
        value, so it must be merged in here.
        """
        return cls.model_validate({**data, "content_hash": content_hash})


@dataclass
class SuggestionStore:
    """Container for all photo suggestions."""

    photos: dict[str, PhotoSuggestions] = field(default_factory=dict)

    def add(self, ps: PhotoSuggestions) -> None:
        self.photos[ps.content_hash] = ps

    def get(self, content_hash: str) -> PhotoSuggestions | None:
        return self.photos.get(content_hash)

    def has(self, content_hash: str) -> bool:
        return content_hash in self.photos

    def hashes(self) -> set[str]:
        return set(self.photos.keys())

    def to_dict(self) -> dict:
        return {
            "photos": {h: ps.to_dict() for h, ps in self.photos.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> SuggestionStore:
        store = cls()
        for content_hash, photo_data in data.get("photos", {}).items():
            store.photos[content_hash] = PhotoSuggestions.from_dict(
                content_hash, photo_data
            )
        return store


# =============================================================================
# File I/O
# =============================================================================


def get_suggestion_store_path() -> Path:
    return Path(__file__).parent / "suggestions.json"


def load_suggestion_store(path: Path | None = None) -> SuggestionStore:
    if path is None:
        path = get_suggestion_store_path()
    if not path.exists():
        return SuggestionStore()
    with open(path, "r") as f:
        return SuggestionStore.from_dict(json.load(f))


def save_suggestion_store(store: SuggestionStore, path: Path | None = None) -> None:
    if path is None:
        path = get_suggestion_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(store.to_dict(), f, indent=2)


# =============================================================================
# Ghost labeling runner
# =============================================================================


def run_ghost_labeling(
    content_hashes: Sequence[str],
    photos_dir: Path,
    photo_index: dict[str, list[str]],
    *,
    store_path: Path | None = None,
    verbose: bool = True,
) -> SuggestionStore:
    """Run bib and face detection on the given photos, storing suggestions.

    Requires heavy ML dependencies (easyocr, cv2, torch, faces backend).
    Imports are done lazily inside this function.

    Args:
        content_hashes: Photo hashes to process.
        photos_dir: Base directory for photo files.
        photo_index: Mapping of content_hash → [relative_paths].
        store_path: Path to suggestions.json (default: standard location).
        verbose: Whether to log progress.

    Returns:
        Updated SuggestionStore with new suggestions added.
    """
    import cv2
    import numpy as np
    import easyocr
    import torch

    from detection import detect_bib_numbers
    from faces import get_face_backend
    from .photo_index import get_path_for_hash
    from warnings_utils import suppress_torch_mps_pin_memory_warning

    store = load_suggestion_store(store_path)

    if not content_hashes:
        return store

    # Initialise ML backends
    if verbose:
        logger.info("Initialising ghost labeling backends...")
    suppress_torch_mps_pin_memory_warning()
    reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available())
    face_backend = get_face_backend()

    # Build provenance from current config
    bib_version = getattr(easyocr, "__version__", "unknown")
    face_model = face_backend.model_info()
    provenance = Provenance(
        backend=f"easyocr+{face_model.name}",
        version=f"easyocr={bib_version},face={face_model.version}",
        config={},
    )

    for i, content_hash in enumerate(content_hashes):
        path = get_path_for_hash(content_hash, photos_dir, photo_index)
        if not path or not path.exists():
            if verbose:
                logger.info(
                    "  [%d/%d] SKIP (file not found): %s...",
                    i + 1, len(content_hashes), content_hash[:8],
                )
            continue

        image_data = path.read_bytes()

        try:
            # --- Bib detection ---
            bib_result = detect_bib_numbers(reader, image_data)
            img_w, img_h = bib_result.original_dimensions

            bib_suggestions: list[BibSuggestion] = []
            for det in bib_result.detections:
                x, y, w, h = normalize_quad(det.bbox, img_w, img_h)
                bib_suggestions.append(BibSuggestion(
                    x=x, y=y, w=w, h=h,
                    number=det.bib_number,
                    confidence=det.confidence,
                ))

            # --- Face detection ---
            image_array = cv2.imdecode(
                np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
            )
            if image_array is None:
                raise ValueError("Could not decode image")
            image_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
            face_h, face_w = image_rgb.shape[:2]

            face_candidates = face_backend.detect_face_candidates(image_rgb)
            face_suggestions: list[FaceSuggestion] = []
            for cand in face_candidates:
                if not cand.passed:
                    continue
                x, y, w, h = normalize_quad(cand.bbox, face_w, face_h)
                face_suggestions.append(FaceSuggestion(
                    x=x, y=y, w=w, h=h,
                    confidence=cand.confidence if cand.confidence is not None else 0.0,
                ))

            store.add(PhotoSuggestions(
                content_hash=content_hash,
                bibs=bib_suggestions,
                faces=face_suggestions,
                provenance=provenance,
            ))

            if verbose:
                logger.info(
                    "  [%d/%d] %s... → %d bibs, %d faces",
                    i + 1, len(content_hashes), content_hash[:8],
                    len(bib_suggestions), len(face_suggestions),
                )
        except Exception as exc:
            if verbose:
                logger.warning(
                    "  [%d/%d] %s... FAILED: %s",
                    i + 1, len(content_hashes), content_hash[:8], exc,
                )

    save_suggestion_store(store, store_path)

    return store
