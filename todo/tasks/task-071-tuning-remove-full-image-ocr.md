# Task 071: Remove full-image OCR fallback

Part of the tuning series (071–077).

## Goal

Remove the full-image OCR fallback from `detect_bib_numbers()`. This simplifies the detection pipeline to a single path (white-region candidates → OCR) and eliminates a source of false positives, unclear candidate lineage, and redundant configuration.

## Background

The pipeline currently has two OCR paths:

1. **White-region candidates** — find bright rectangular regions, validate geometry/brightness, run OCR on each region. This is the principled path.
2. **Full-image OCR** — run EasyOCR on the entire image, filter by a separate confidence threshold (`FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`). This is a fallback for when path 1 misses a bib.

The full-image fallback is the wrong fix for a real problem:

- It runs OCR on the entire photo — runners, signs, banners, timing clocks — producing FPs from random text
- It requires its own higher confidence threshold to compensate for the noise, adding a second tuning dimension
- Its detections have no proper candidate lineage (`source_candidate=None`), making diagnostic traces impossible
- It masks weaknesses in candidate detection instead of fixing them
- Every bib it finds is a bib that candidate detection *should* have found

Removing it makes the pipeline uniform and gives honest signal about where candidate detection needs improvement. The benchmark quantifies the actual TP cost.

## Context

- `detection/detector.py:152-159` — the full-image OCR call and candidate/detection merging
- `detection/detector.py:31-79` — `extract_bib_detections()` function (used only by full-image path)
- `config.py:71` — `FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`
- `detection/types.py:23` — `DetectionSource = Literal["white_region", "full_image"]`
- `detection/regions.py:9,37` — docstrings mentioning full_image
- `docs/DETECTION.md` — pipeline documentation

## Test-first approach

Write tests before making changes:

### New: `tests/test_no_full_image_ocr.py`

```python
"""Verify that full-image OCR has been removed from the detection pipeline."""

def test_detect_bib_numbers_has_no_full_image_source():
    """All detections must have source='white_region'."""
    # Run detection on a test image (slow, needs reader)
    # Assert every detection in result.detections has source == "white_region"

def test_detection_source_type_is_white_region_only():
    """DetectionSource literal should only allow 'white_region'."""
    from detection.types import DetectionSource
    # Verify "full_image" is not in the type

def test_full_image_confidence_threshold_removed():
    """FULL_IMAGE_CONFIDENCE_THRESHOLD should not exist in config."""
    import config
    assert not hasattr(config, "FULL_IMAGE_CONFIDENCE_THRESHOLD")

def test_extract_bib_detections_removed():
    """The full-image helper function should not exist."""
    import detection.detector as det
    assert not hasattr(det, "extract_bib_detections")
```

Mark the first test `@pytest.mark.slow` (needs EasyOCR reader).

## Changes

### Modified: `detection/detector.py`

1. Remove the full-image OCR block (lines 152-159):
   ```python
   # DELETE:
   full_image_detections, full_image_candidates = extract_bib_detections(...)
   all_detections.extend(full_image_detections)
   all_candidates.extend(full_image_candidates)
   ```

2. Remove `extract_bib_detections()` function (lines 31-79). It is only used by the full-image path.

3. Remove the `FULL_IMAGE_CONFIDENCE_THRESHOLD` import.

### Modified: `config.py`

Remove `FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`.

### Modified: `detection/types.py`

Simplify:
```python
# Before:
DetectionSource = Literal["white_region", "full_image"]

# After:
DetectionSource = Literal["white_region"]
```

Update `Detection` docstring to remove "full_image" references. Remove the `source_candidate` note about "None for full_image" — all detections now have a source candidate.

### Modified: `detection/regions.py`

Update docstrings that mention "full_image" detection method.

### Modified: `docs/DETECTION.md`

Remove full-image OCR section from pipeline documentation.

### Modified: `docs/RESEARCH_QUESTIONS.md`

Remove `FULL_IMAGE_CONFIDENCE_THRESHOLD` reference (line 34).

## Verification

```bash
# TDD: write tests first, verify they fail
venv/bin/python -m pytest tests/test_no_full_image_ocr.py -v

# Make changes, verify tests pass
venv/bin/python -m pytest tests/test_no_full_image_ocr.py -v

# Full suite
venv/bin/python -m pytest

# Benchmark to measure impact
venv/bin/python bnr.py benchmark run
# Compare F1/precision/recall with previous run
```

## Acceptance criteria

- [ ] `extract_bib_detections()` removed from `detection/detector.py`
- [ ] `FULL_IMAGE_CONFIDENCE_THRESHOLD` removed from `config.py`
- [ ] `DetectionSource` no longer includes `"full_image"`
- [ ] All detections have `source="white_region"` and a `source_candidate`
- [ ] TDD tests pass
- [ ] All existing tests pass (`venv/bin/python -m pytest`)
- [ ] Benchmark run completed — delta documented in commit message

## Scope boundaries

- **In scope**: remove full-image OCR, update types, update docs, benchmark impact
- **Out of scope**: improving candidate detection to compensate (that's a future task informed by the benchmark delta)
- **Do not** change the white-region candidate pipeline — only remove the fallback
