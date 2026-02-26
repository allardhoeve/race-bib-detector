# task-030: Implement face-bib autolink predictor

**Status:** pending

## Goal

Implement the autolink algorithm that produces predicted bib-face link pairs from detected bib
boxes and detected face boxes, forming the input to `score_links()`.

## Background

`score_links()` in `scoring.py` expects `predicted_pairs: list[tuple[BibBox, FaceBox]]`.
Currently `run_benchmark()` stubs `link_tp=0`. This task builds the pure predictor function
that generates those pairs.

## Changes

### `faces/autolink.py` (new file)

```python
@dataclass
class AutolinkResult:
    pairs: list[tuple[BibBox, FaceBox]]   # predicted (bib, face) associations
    provenance: list[str]                  # "single_face" | "cluster_inherit" per pair

def predict_links(
    bib_boxes: list[BibBox],
    face_boxes: list[FaceBox],
    bib_confidence_threshold: float = 0.5,
) -> AutolinkResult:
    """Rule-based autolink predictor for a single photo.

    Rules (applied in order):
    1. Single face rule: if exactly 1 face and exactly 1 high-confidence bib → link them.
    2. Multi-face rule: if multiple faces, link each face to the spatially nearest bib
       whose confidence >= threshold AND whose centroid is in the face's torso region
       (below face box, within ±1 bib-width horizontally). One face per bib max.

    Args:
        bib_boxes: Detected bib boxes for this photo (normalized [0,1] coords).
        face_boxes: Detected face boxes for this photo (normalized [0,1] coords).
        bib_confidence_threshold: Minimum bib detection confidence for autolink eligibility.
    """
```

Helper (module-private):
```python
def _torso_region(face_box: FaceBox) -> tuple[float, float, float, float]:
    """Returns expected torso bounding box (x, y, w, h) in normalized [0,1] coords.

    The torso is estimated as the region directly below the face box, roughly
    1–3× face heights below the face centroid and within ±1 face-width horizontally.
    """
```

## Tests

File: `tests/test_autolink.py`

- `test_single_face_single_bib()` — one face + one high-conf bib → exactly one link.
- `test_single_face_low_conf_bib()` — bib below threshold → empty result.
- `test_multiple_faces_multiple_bibs()` — spatial matching; assert correct face-bib assignments.
- `test_no_faces()` — empty face list → `AutolinkResult(pairs=[], provenance=[])`.
- `test_no_bibs()` — empty bib list → `AutolinkResult(pairs=[], provenance=[])`.

## Scope boundary

- Pure function — no DB access, no runner calls, no UI.
- Does **not** implement cluster-based inheritance (deferred to task-031 or later).
- Does **not** wire into the benchmark runner (that is task-031).
