# Task 087: Remove full-image OCR fallback

Part of the tuning series (085-094).

**Depends on:** task-086 (detection/ reorg) — or can be done before if targeting `detection/detector.py` directly

## Goal

Remove the full-image OCR fallback from `detect_bib_numbers()`. Simplifies the bib detection pipeline to a single path (white-region candidates → OCR) and eliminates false positives, unclear lineage, and redundant config.

## Background

Two OCR paths exist today:

1. **White-region candidates** — find bright rectangular regions, validate, run OCR per region. The principled path.
2. **Full-image OCR** — run EasyOCR on the entire image with `FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`. A fallback that masks candidate detection weaknesses.

The fallback produces FPs from signs/banners/clocks, requires its own tuning dimension, and creates detections with no candidate lineage (`source_candidate=None`). Every bib it finds is one that candidate detection *should* have found.

## Context

Post-086 paths (or current paths if done before 086):
- `detection/bib/detector.py` (or `detection/detector.py`): full-image OCR block + `extract_bib_detections()`
- `detection/bib/types.py` (or `detection/types.py`): `DetectionSource = Literal["white_region", "full_image"]`
- `config.py`: `FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`

## Test-first approach

```python
def test_detection_source_type_is_white_region_only():
    from detection.bib.types import DetectionSource  # or detection.types
    # Verify "full_image" is not in the type

def test_full_image_confidence_threshold_removed():
    import config
    assert not hasattr(config, "FULL_IMAGE_CONFIDENCE_THRESHOLD")

def test_extract_bib_detections_removed():
    import detection.bib.detector as det  # or detection.detector
    assert not hasattr(det, "extract_bib_detections")
```

## Changes

### Modified: `detection/bib/detector.py`

1. Delete `extract_bib_detections()` function
2. Delete the full-image OCR block that calls it
3. Remove `FULL_IMAGE_CONFIDENCE_THRESHOLD` import

### Modified: `config.py`

Remove `FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5`.

### Modified: `detection/bib/types.py`

```python
# Before:
DetectionSource = Literal["white_region", "full_image"]
# After:
DetectionSource = Literal["white_region"]
```

Update `Detection` docstring — all detections now have a `source_candidate`.

### Modified: docs

Update `docs/DETECTION.md` and `docs/RESEARCH_QUESTIONS.md` to remove full-image references.

## Verification

```bash
venv/bin/python -m pytest
venv/bin/python bnr.py benchmark run  # measure impact
```

## Acceptance criteria

- [ ] `extract_bib_detections()` removed
- [ ] `FULL_IMAGE_CONFIDENCE_THRESHOLD` removed from config
- [ ] `DetectionSource` no longer includes `"full_image"`
- [ ] All detections have `source="white_region"` and a `source_candidate`
- [ ] TDD tests pass
- [ ] All existing tests pass
- [ ] Benchmark delta documented in commit message

## Scope boundaries

- **In scope**: remove fallback, update types, docs, benchmark impact
- **Out of scope**: improving candidate detection to compensate
- **Do not** change the white-region candidate pipeline
