"""Per-photo completeness model: tracks whether all labeling dimensions are done."""
from __future__ import annotations

from dataclasses import dataclass

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
)
from benchmarking.label_utils import is_face_labeled


@dataclass
class PhotoCompleteness:
    content_hash: str
    bib_labeled: bool
    face_labeled: bool
    links_labeled: bool   # True when trivially N/A (0 bib or face boxes) or GT entry exists
    bib_box_count: int
    face_box_count: int

    @property
    def is_complete(self) -> bool:
        return self.bib_labeled and self.face_labeled and self.links_labeled

    @property
    def is_known_negative(self) -> bool:
        """Both dimensions labeled and both have zero boxes — no link step needed."""
        return (
            self.bib_labeled
            and self.face_labeled
            and self.bib_box_count == 0
            and self.face_box_count == 0
        )


def photo_completeness(content_hash: str) -> PhotoCompleteness:
    """Compute completeness for a single photo from all GT stores."""
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    bib_label = bib_gt.get_photo(content_hash)
    face_label = face_gt.get_photo(content_hash)

    bib_labeled = bool(bib_label and bib_label.labeled)
    face_labeled = bool(face_label and is_face_labeled(face_label))

    bib_box_count = len(bib_label.boxes) if bib_label else 0
    face_box_count = len(face_label.boxes) if face_label else 0

    # links_labeled: trivially True when no bib or face boxes exist
    if bib_box_count == 0 or face_box_count == 0:
        links_labeled = True
    else:
        # Requires task-007 LinkGroundTruth; gracefully defaults to True if unavailable
        try:
            from benchmarking.ground_truth import load_link_ground_truth
            link_gt = load_link_ground_truth()
            links_labeled = content_hash in link_gt.photos
        except (ImportError, AttributeError):
            links_labeled = True

    return PhotoCompleteness(
        content_hash=content_hash,
        bib_labeled=bib_labeled,
        face_labeled=face_labeled,
        links_labeled=links_labeled,
        bib_box_count=bib_box_count,
        face_box_count=face_box_count,
    )


def get_all_completeness() -> list[PhotoCompleteness]:
    """Return completeness for every photo that has at least one labeling dimension done.

    Only photos that appear in the bib or face GT are included — unlabeled photos
    are not shown because they have not been touched at all.
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    touched = set(bib_gt.photos) | set(face_gt.photos)
    return [photo_completeness(h) for h in sorted(touched)]
