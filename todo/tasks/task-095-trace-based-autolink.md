# Task 095: Trace-based autolink

Structural prerequisite for task-093 (refinement). Split into 095a (rename) and 095b (this task).

**Depends on:** task-095a (rename BibBox/FaceBox), task-088 (bib traces), task-089 (face traces)

## Problem

Autolink operates on boxes (`BibBox`, `FaceBox`) when it should operate on traces — the richest, most-downstream per-photo data. This creates a gap: clustering writes to traces, linking writes to boxes, and three sites use fragile positional hacks to bridge them.

## Goal

Make `predict_links` work on traces. Introduce `TraceLink` to replace `AutolinkResult`. Delete the box-based autolink path entirely.

## Design

### TraceLink

```python
@dataclass
class TraceLink:
    """A link between a face trace and a bib trace within one photo."""
    face_trace: FaceCandidateTrace
    bib_trace: BibCandidateTrace
    provenance: str      # "single_face", "spatial"
    distance: float      # centroid distance (debug/introspection)
```

### predict_links on traces

```python
def predict_links(
    bib_traces: list[BibCandidateTrace],
    face_traces: list[FaceCandidateTrace],
) -> list[TraceLink]:
```

Traces always have coordinates (no legacy migration), so `has_coords` filtering is unnecessary. The spatial logic (torso region, centroid matching) reads `x, y, w, h` from traces — same fields, same math.

### SinglePhotoResult

```python
# Replace:
autolink: AutolinkResult | None = None
# With:
links: list[TraceLink] = field(default_factory=list)
```

### What gets deleted

- `AutolinkResult` class
- `.to_bib_box()` on `BibCandidateTrace`
- `.to_face_box()` on `FaceCandidateTrace`
- Box cache properties on `SinglePhotoResult` (`_bib_boxes_cache`, `_face_boxes_cache`)

### Consumers to update

1. **`pipeline/single_photo.py`** — call `predict_links` with traces, store `list[TraceLink]`, remove box caching logic
2. **`scan/persist.py`** — map `TraceLink` to DB detection IDs directly (no more `list.index()` hack)
3. **`benchmarking/runner.py`** — build `BibFaceLink` from `TraceLink` directly (no more `list.index()` hack); back-propagation of `cluster_id` to boxes no longer needed
4. **`benchmarking/scoring.py`** — `score_links()` accepts `list[TraceLink]` for predicted side
5. **Tests** — `test_autolink.py`, `test_pipeline.py`, `test_pipeline_types.py`, `test_process_image_autolink.py`, `test_link_scoring.py`, `test_runner.py`

## Acceptance criteria

- [ ] `TraceLink` dataclass defined
- [ ] `predict_links` accepts traces, returns `list[TraceLink]`
- [ ] `AutolinkResult` deleted
- [ ] `.to_bib_box()` / `.to_face_box()` deleted
- [ ] `SinglePhotoResult.links` replaces `.autolink`
- [ ] Box cache removed from `SinglePhotoResult`
- [ ] All three positional-hack sites eliminated
- [ ] All existing tests pass
- [ ] Task-093 unblocked

## Architectural rule

**Labels are banned from `pipeline/`.** After this task, no file under `pipeline/` may import, create, or reference `BibLabel` or `FaceLabel` (currently `BibBox`/`FaceBox`). Labels are ground truth / labeling types that live in `benchmarking/`. The pipeline produces only traces and trace links. Consumers that need label-shaped data (DB persistence, scoring) read the relevant fields from traces directly.

`BibLabel`/`FaceLabel` definitions may remain in `pipeline/types.py` temporarily for backward compat, but pipeline code must not use them. Task-095a moves them out.

## Scope boundaries

- **In scope**: trace-based linking, deleting box derivation from traces, updating consumers, enforcing labels-out-of-pipeline rule
- **Out of scope**: renaming BibBox/FaceBox (095a), refinement loop (093), set-level container
- `BibLabel`/`FaceLabel` (formerly BibBox/FaceBox) stay for GT — they are not pipeline types
- `BibFaceLink` stays — GT serialization format (index pairs)
