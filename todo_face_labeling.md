# Face Labeling Plan

Date: 2026-02-07

## Summary
Add a dedicated face-labeling UI to capture face counts and face-specific tags
without slowing down the bib labeling workflow. Store face labels in the same
ground truth file as bib labels for convenience, and migrate existing data.

## Goals
- Label face counts per photo (ground truth for face detection recall).
- Apply face-specific tags (prefixed `face_`) with fast keyboard shortcuts.
- Keep bib labeling UI intact and focused on bibs.
- Record face labeling stats and enable face-specific filtering.
- Expose face labeling runs in the same benchmark tooling.

## Non-Goals (Initial)
- No face boxes or identity labels.
- No clustering evaluation (counts only).
- No automated face-label suggestion.

## Data Model
- Single `benchmarking/ground_truth.json` continues to store all labels.
- Extend `PhotoLabel` with:
  - `face_count: int | None`
  - `face_tags: list[str]`
- Add a distinct `ALLOWED_FACE_TAGS` set.
- Keep bib tags unchanged (no rename or prefix changes).

## Migration
- Bump schema version.
- Existing labels:
  - `face_count = None`
  - `face_tags = []`
- Ensure backwards compatibility in `from_dict` for older files.

## Face Labeling UI
- New route: `/faces/labels` (separate from bib labeling).
- Dedicated form:
  - Face count numeric input.
  - Face-specific tags (checkboxes).
  - Split selector (iteration/full).
- Keyboard shortcuts focused on face tagging:
  - Cmd/Ctrl+N for `face_no_faces`
  - Cmd/Ctrl+T for `face_tiny_faces`
  - Cmd/Ctrl+O for `face_occluded_faces`
  - Cmd/Ctrl+B for `face_blurry_faces`
- Filtering options:
  - all / labeled / unlabeled
  - optional filter by face tag (future)

## Benchmark Stats
- Extend `benchmark stats` to report:
  - total photos with face labels
  - distribution of face counts
  - counts by face tag

## Benchmark UI
- Add “Face labels” nav entry to go to new face-labeling UI.
- Keep existing bib labeling UI unchanged.

## TODO
- [x] Extend ground truth schema for face labels and tags (version bump + migration).
- [x] Define allowed face tags + keyboard mapping.
- [x] Build face labeling UI (separate from bib UI).
- [x] Add face label stats to `benchmark stats`.
- [x] Add navigation links between bib and face labeling pages.
