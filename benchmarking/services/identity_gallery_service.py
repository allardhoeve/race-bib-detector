"""Aggregation service for the identity gallery QA view."""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
)
from benchmarking.photo_metadata import load_photo_metadata


@dataclass
class FaceAppearance:
    """A single face occurrence with optional linked bib info."""

    content_hash: str
    face_box_index: int
    bib_number: str | None = None
    bib_box_index: int | None = None
    frozen: bool = False


@dataclass
class IdentityGroup:
    """All face appearances for a single identity."""

    name: str
    faces: list[FaceAppearance] = field(default_factory=list)

    @property
    def distinct_bib_numbers(self) -> list[str]:
        """Unique bib numbers across all faces, sorted."""
        return sorted({f.bib_number for f in self.faces if f.bib_number})

    @property
    def frozen_count(self) -> int:
        return sum(1 for f in self.faces if f.frozen)

    @property
    def new_count(self) -> int:
        return sum(1 for f in self.faces if not f.frozen)


def _sort_key(group: IdentityGroup) -> tuple[int, int, str]:
    """Sort: errors first (multiple bibs), then by name; Unassigned last."""
    name = group.name
    if name == "Unassigned":
        return (2, 0, "")
    has_error = 0 if len(group.distinct_bib_numbers) > 1 else 1
    return (0, has_error, name.lower())


def get_identity_gallery() -> list[IdentityGroup]:
    """Return all identities with their face+bib appearances.

    Only includes keep-scoped face boxes with coordinates.
    """
    face_gt = load_face_ground_truth()
    bib_gt = load_bib_ground_truth()
    link_gt = load_link_ground_truth()
    frozen_set = set(load_photo_metadata().frozen_hashes())

    # Build a lookup: (content_hash, face_index) → (bib_number, bib_box_index)
    bib_for_face: dict[tuple[str, int], tuple[str, int]] = {}
    for content_hash, links in link_gt.photos.items():
        bib_label = bib_gt.get_photo(content_hash)
        if not bib_label:
            continue
        for link in links:
            if link.bib_index < len(bib_label.boxes):
                bib_box = bib_label.boxes[link.bib_index]
                bib_for_face[(content_hash, link.face_index)] = (
                    bib_box.number,
                    link.bib_index,
                )

    # Group faces by identity
    groups: dict[str, list[FaceAppearance]] = {}
    for content_hash, label in face_gt.photos.items():
        for box_index, box in enumerate(label.boxes):
            if box.scope != "keep" or not box.has_coords:
                continue

            identity = box.identity or "Unassigned"
            bib_info = bib_for_face.get((content_hash, box_index))

            appearance = FaceAppearance(
                content_hash=content_hash,
                face_box_index=box_index,
                bib_number=bib_info[0] if bib_info else None,
                bib_box_index=bib_info[1] if bib_info else None,
                frozen=content_hash in frozen_set,
            )
            groups.setdefault(identity, []).append(appearance)

    result = []
    for name, faces in groups.items():
        # Sort within group: frozen first, then by hash for stability
        faces.sort(key=lambda f: (not f.frozen, f.content_hash))
        result.append(IdentityGroup(name=name, faces=faces))
    result.sort(key=_sort_key)
    return result
