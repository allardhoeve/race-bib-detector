# TODO - Labeling UI

Goal: Make labeling fast and consistent for manual ground truth.

## Decisions

- **Speed priority**: The UI must be fast and lag-free. Do not block on detection results.
- **No live detection**: Detection takes ~3 seconds per photo, which is too slow for interactive labeling. If detection results are needed, they should be pre-computed in batch and optionally displayed from cache.
- **Depends on**: todo_labeling.md (scanner and ground_truth.json structure must exist first).

## Tasks

- [x] Build a simple UI to:
  - display photo immediately (no lag)
  - enter bib numbers
  - toggle tags via checkboxes
  - save/update ground truth
  - navigate to next/previous photo
- [x] Support duplicate detection and edit existing entries (via content hash lookup).
- [x] Provide a view that identifies unlabeled photos in `photos/`.
- [ ] Optionally show cached detection results if they exist (but never block on computing them).

## Deliverable

- [x] A labeling UI that allows rapid annotation of 200+ photos without friction.

## Implementation

- `benchmarking/labeling_app.py` - Flask web UI for labeling

Usage:
```bash
python -m benchmarking.cli ui          # Launch labeling UI on http://localhost:30002
```

Features:
- Keyboard shortcuts: ← → navigate, Enter save & next, Esc clear bibs
- Filter dropdown: All / Unlabeled only / Labeled only
- Dark theme for reduced eye strain during long labeling sessions
