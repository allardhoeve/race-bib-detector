# TODO - Labeling UI

Goal: Make labeling fast and consistent for manual ground truth.

## Decisions

- **Speed priority**: The UI must be fast and lag-free. Do not block on detection results.
- **No live detection**: Detection takes ~3 seconds per photo, which is too slow for interactive labeling. If detection results are needed, they should be pre-computed in batch and optionally displayed from cache.
- **Depends on**: todo_labeling.md (scanner and ground_truth.json structure must exist first).

## Tasks

- [ ] Build a simple UI to:
  - display photo immediately (no lag)
  - enter bib numbers
  - toggle tags via checkboxes
  - save/update ground truth
  - navigate to next/previous photo
- [ ] Support duplicate detection and edit existing entries (via content hash lookup).
- [ ] Provide a view that identifies unlabeled photos in `photos/`.
- [ ] Optionally show cached detection results if they exist (but never block on computing them).

## Deliverable

- A labeling UI that allows rapid annotation of 200+ photos without friction.
