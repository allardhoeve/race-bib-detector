# Task 038: Explicit completion state for faces + completion service

Independent of other pending tasks.

## Goal

Replace inferred face-labeling completion with an explicit `labeled` flag (mirroring
bibs), and introduce a `CompletionService` that answers workflow-readiness questions.
Routes stop containing knowledge about what "labeled" means; they simply ask the service.

## Background

Completion is currently determined by heuristics:

- **Bibs**: `BibPhotoLabel.labeled: bool` — set explicitly on save. ✅
- **Faces**: `is_face_labeled()` returns `bool(label.boxes) or bool(label.tags)`. A photo
  with no faces that has been reviewed but has no boxes/tags looks identical to one that
  has never been visited. ❌
- **Links**: `completeness.py` auto-marks links done if `bib_count == 0 OR face_count == 0`,
  regardless of whether the other dimension has been labeled. ❌

This means the linking queue (`/associations/`) shows photos where bibs or faces haven't
been reviewed yet, and `PhotoCompleteness.is_complete` is unreliable.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where does face `labeled` live? | `FacePhotoLabel.labeled: bool = False`, set to `True` on any save — same pattern as `BibPhotoLabel` |
| What counts as "links ready"? | Both `bib_labeled=True` AND `face_labeled=True`. Trivially done (no link step) if additionally `bib_count==0 OR face_count==0` |
| Who answers "which photos are ready for linking"? | New `CompletionService` in `benchmarking/services/completion_service.py` |
| Do routes call GT directly for completion queries? | No — routes call `CompletionService`; GT internals stay encapsulated |
| Does saving an empty link list count as "links reviewed"? | Yes — `content_hash in link_gt.photos` already captures this; no new field needed |

## Changes: `benchmarking/ground_truth.py`

### Modified: `FacePhotoLabel`

Add `labeled: bool = False` field:

```python
class FacePhotoLabel(BaseModel):
    content_hash: str
    boxes: list[FaceBox] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    labeled: bool = False          # ← new: True once a human has reviewed this photo's faces
```

### Modified: `FaceGroundTruth.to_dict()` and `from_dict()`

Persist the new field. `from_dict` must default to `False` for existing entries (backwards
compat — old JSON has no `labeled` key).

```python
# to_dict: include labeled in each photo entry
# from_dict: FacePhotoLabel(**photo_data) already handles default via Pydantic
```

## Changes: `benchmarking/label_utils.py`

### Modified: `is_face_labeled()`

```python
def is_face_labeled(label: FacePhotoLabel) -> bool:
    """True once a human has explicitly saved face labels for this photo."""
    return label.labeled
```

Remove the old heuristic (`bool(label.boxes) or bool(label.tags)`).

## Changes: `benchmarking/services/face_service.py`

### Modified: `save_face_label()`

Set `labeled=True` when saving, same as `bib_service.save_bib_label()` does:

```python
label = FacePhotoLabel(
    content_hash=full_hash,
    boxes=boxes,
    tags=tags,
    labeled=True,   # ← new
)
```

## Changes: `benchmarking/services/completion_service.py` (new file)

Central service for workflow-readiness queries. Routes use this; they do not inspect GT
directly for completion logic.

```python
"""Workflow completion queries: which photos are ready for each labeling step."""
from __future__ import annotations

from benchmarking.ground_truth import load_bib_ground_truth, load_face_ground_truth, load_link_ground_truth
from benchmarking.label_utils import is_face_labeled
from benchmarking.photo_index import load_photo_index


def get_link_ready_hashes() -> list[str]:
    """Return sorted hashes of photos where both bib and face labeling are done.

    These are the only photos that should appear in the linking queue.
    Photos where bib_count==0 OR face_count==0 are included (link step is trivially done,
    but they should still be visible/skippable in the linking UI).
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    index = load_photo_index()

    ready = []
    for h in sorted(index.keys()):
        bib_label = bib_gt.get_photo(h)
        face_label = face_gt.get_photo(h)
        bib_labeled = bool(bib_label and bib_label.labeled)
        face_labeled = bool(face_label and face_label.labeled)
        if bib_labeled and face_labeled:
            ready.append(h)
    return ready


def get_unlinked_hashes() -> list[str]:
    """Return link-ready hashes that have not yet had links saved."""
    link_gt = load_link_ground_truth()
    return [h for h in get_link_ready_hashes() if h not in link_gt.photos]


def bib_count_for(content_hash: str) -> int:
    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(content_hash)
    return len(label.boxes) if label else 0


def face_count_for(content_hash: str) -> int:
    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(content_hash)
    return len(label.boxes) if label else 0
```

## Changes: `benchmarking/completeness.py`

### Modified: `photo_completeness()`

Fix the trivial links logic — only auto-True when **both** dimensions are explicitly labeled:

```python
# Before:
if bib_box_count == 0 or face_box_count == 0:
    links_labeled = True

# After:
if bib_labeled and face_labeled and (bib_box_count == 0 or face_box_count == 0):
    links_labeled = True
```

Also remove the `try/except ImportError` fallback — `load_link_ground_truth` is always available.

## Changes: `benchmarking/routes/ui/labeling.py`

### Modified: `associations_index()` and `association_photo()`

Replace direct `sorted(index.keys())` with `CompletionService.get_link_ready_hashes()`.
Replace the inline `next_unlabeled_url` loop with `get_unlinked_hashes()`.

```python
from benchmarking.services.completion_service import get_link_ready_hashes, get_unlinked_hashes

# associations_index: use get_link_ready_hashes() instead of sorted(index.keys())
# association_photo: same for the hashes list; next_unlabeled_url uses get_unlinked_hashes()
```

Routes do **not** contain any logic about what "labeled" means.

## Tests

`tests/test_completion_service.py`:

- `test_get_link_ready_hashes_requires_both_labeled()` — photo with only bib labeled is excluded
- `test_get_link_ready_hashes_requires_face_labeled()` — photo with only face labeled is excluded
- `test_get_link_ready_hashes_includes_when_both_done()` — photo with both labeled is included
- `test_get_unlinked_hashes_excludes_already_linked()` — photo in link_gt is excluded
- `test_trivial_links_not_auto_done_when_face_unlabeled()` — `photo_completeness()` does not mark links done if face_labeled=False even with 0 boxes

`tests/test_ground_truth.py` (extend existing):

- `test_face_photo_label_defaults_labeled_false()` — new labels default to unlabeled
- `test_face_ground_truth_roundtrip_preserves_labeled()` — to_dict / from_dict preserves field
- `test_face_ground_truth_from_dict_missing_labeled_defaults_false()` — backwards compat

## Scope boundaries

- **In scope**: `FacePhotoLabel.labeled`, `is_face_labeled()`, `face_service`, `completeness.py`, new `CompletionService`, linking route queue filter
- **Out of scope**: task-039 (tab navigation), bib labeling (already explicit), link GT schema changes
- **Do not** add `links_reviewed` field to `LinkGroundTruth` — saving links (even `[]`) is already an explicit action
- **Do not** change the face labeling UI — saving already triggers `save_face_label()`
