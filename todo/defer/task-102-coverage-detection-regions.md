# Task 102: Test coverage for bib candidate regions

Independent. No dependencies on other tasks.

**TDD approach: `tdd: strangler rewrite`**

## Goal

Cover `detection/regions.py` — the primary bib candidate pipeline at 10% coverage. These functions find white rectangular regions that could be bib numbers and validate OCR bounding boxes against the same criteria.

## Background

Coverage analysis (2026-03-02) found both `validate_detection_region` and `find_bib_candidates` almost entirely untested. Both are pure functions operating on numpy arrays. Testable with synthetic images (white rectangles on dark backgrounds).

## Context

- `detection/regions.py` — `validate_detection_region()` and `find_bib_candidates()`
- `detection/types.py` — `BibCandidate` dataclass (the return type)
- `geometry.py` — `Bbox`, `bbox_to_rect` (coordinate conversion)
- `config.py` — filter thresholds: `MIN_CONTOUR_AREA`, `WHITE_THRESHOLD`, `MIN_ASPECT_RATIO`, `MAX_ASPECT_RATIO`, `MIN_RELATIVE_AREA`, `MAX_RELATIVE_AREA`, `MEDIAN_BRIGHTNESS_THRESHOLD`, `MEAN_BRIGHTNESS_THRESHOLD`, `REGION_PADDING_RATIO`

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| How to create test images? | `np.zeros(...)` + `cv2.rectangle(...)` to draw white boxes on dark background |
| Override config thresholds in tests? | Pass explicit values where the function accepts them; for config-dependent params, use images that clearly pass or fail default thresholds |

## Changes

No structural changes. Each function is reimplemented in place via the strangler cycle.

## Tests

### New: `tests/test_detection_regions.py`

**`validate_detection_region`**:
- `test_valid_bright_region_passes()` — white bbox on bright region passes all filters
- `test_rejects_bad_aspect_ratio()` — very tall/narrow bbox rejected
- `test_rejects_too_small_relative_area()` — tiny bbox relative to image rejected
- `test_rejects_dark_region()` — dark region below brightness threshold
- `test_zero_size_bbox()` — degenerate bbox returns rejected candidate

**`find_bib_candidates`**:
- `test_finds_white_rectangle()` — single white rect on black background found
- `test_rejects_small_contour()` — tiny white speck below `min_area` filtered out
- `test_include_rejected_flag()` — with `include_rejected=True`, rejected candidates included
- `test_passed_candidates_get_padding()` — passed candidate bbox is padded
- `test_multiple_candidates()` — two white rectangles both found
- `test_no_candidates_on_black_image()` — all-black image returns empty

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `detection/regions.py` coverage >= 85%
- [ ] Both functions exercised with passing and rejecting cases
- [ ] No `_old_*` remnants left in codebase

## Scope boundaries

- **In scope**: `validate_detection_region`, `find_bib_candidates`
- **Out of scope**: `detection/detector.py` (requires ML model, acceptable gap)
- **Do not** modify function signatures or behavior
