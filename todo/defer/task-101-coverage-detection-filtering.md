# Task 101: Test coverage for detection filtering

Independent. No dependencies on other tasks.

**TDD approach: `tdd: strangler rewrite`**

## Goal

Cover `detection/filtering.py` — core detection-quality logic at 38% coverage. These functions decide which bib detections survive and which get removed. Regressions here let false positives through silently.

## Background

Coverage analysis (2026-03-02) found `filter_small_detections`, `filter_overlapping_detections`, and several branches of `choose_detection_to_remove` untested. All three are pure functions operating on `Detection` objects with no I/O.

## Context

- `detection/filtering.py` — the three functions under test
- `detection/types.py` — `Detection` dataclass (constructor: `bib_number`, `confidence`, `bbox`, `source`)
- `detection/bbox.py` — `bbox_area`, `bbox_iou`, `bbox_overlap_ratio` (already 82% covered)
- `detection/validation.py` — `is_substring_bib` (already 100% covered)
- `config.py` — threshold constants: `MIN_DETECTION_AREA_RATIO`, `IOU_OVERLAP_THRESHOLD`, `COVERAGE_OVERLAP_THRESHOLD`, `SUBSTRING_CONFIDENCE_RATIO`

## Changes

No structural changes. Each function is reimplemented in place via the strangler cycle.

## Tests

### New: `tests/test_detection_filtering.py`

**`filter_small_detections`**:
- `test_keeps_large_enough_detection()` — detection area/region ratio above threshold passes
- `test_removes_small_detection()` — ratio below threshold filtered out
- `test_empty_list_returns_empty()` — no crash on empty input
- `test_zero_region_area_returns_all()` — edge case: division guard

**`filter_overlapping_detections`**:
- `test_non_overlapping_kept()` — two distant detections both survive
- `test_overlapping_keeps_longer_bib()` — "620" beats "6" when overlapping
- `test_overlapping_substring_keeps_longer()` — substring relationship resolved correctly
- `test_single_detection_returned()` — single-element list passes through
- `test_empty_list_returns_empty()`

**`choose_detection_to_remove`**:
- `test_substring_keeps_longer()` — "6" is substring of "620", remove "6"
- `test_substring_shorter_high_confidence()` — short bib with much higher confidence wins
- `test_no_substring_more_digits_wins()` — "123" beats "45"
- `test_same_length_higher_confidence_wins()` — "123" at 0.9 beats "456" at 0.5

**`detections_overlap`**:
- `test_overlap_by_iou()` — overlapping boxes detected via IoU
- `test_overlap_by_coverage()` — small box inside large box detected via coverage ratio
- `test_no_overlap()` — distant boxes return False

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `detection/filtering.py` coverage >= 90%
- [ ] All branches of `choose_detection_to_remove` exercised (substring both directions, same-length, different-length)
- [ ] No `_old_*` remnants left in codebase

## Scope boundaries

- **In scope**: all four functions in `detection/filtering.py`
- **Out of scope**: `detection/bbox.py` (already covered), `detection/validation.py` (already 100%)
- **Do not** modify function signatures or behavior
