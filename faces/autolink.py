"""Rule-based bib-face autolink predictor (task-030)."""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarking.ground_truth import BibBox, FaceBox


@dataclass
class AutolinkResult:
    """Result of the autolink predictor for a single photo."""

    pairs: list[tuple[BibBox, FaceBox]] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)


def _torso_region(face_box: FaceBox) -> tuple[float, float, float, float]:
    """Return estimated torso bounding box (x, y, w, h) in normalised [0,1] coords.

    The torso is estimated as the region directly below the face box, roughly
    1–3× face heights below the face and within ±1 face-width horizontally.
    """
    fw = face_box.w
    fh = face_box.h
    cx = face_box.x + fw / 2
    ty = face_box.y + fh      # starts at bottom edge of face
    th = 2 * fh               # extends 2 face-heights downward
    tw = 2 * fw               # ±1 face-width from centre
    tx = cx - fw              # = cx - tw/2
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
