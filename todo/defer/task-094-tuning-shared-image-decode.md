# Task 094: Shared image decode — `detect_bib_numbers` accepts pre-decoded image

Part of the tuning series (085-094). Small optimization.

**Depends on:** task-085 (pipeline/ package)

## Goal

Make `detect_bib_numbers()` accept an optional pre-decoded image, eliminating the last redundant decode. After task-081, `run_single_photo()` already decodes the image once for face detection. But bib detection still receives raw bytes and decodes internally.

## Background

Post-081, `run_single_photo()` decodes the image once with `cv2.imdecode()`. Face detection uses `image_rgb` directly. But bib detection is called as:

```python
bib_result = detect_fn(reader, image_data, artifact_dir=artifact_dir)
```

Inside, `detect_bib_numbers()` calls `run_pipeline()` which decodes `image_data` again. This is the last remaining double-decode.

## Changes

### Modified: `detection/bib/detector.py`

Add optional `image_rgb` parameter:

```python
def detect_bib_numbers(
    reader, image_data, artifact_dir=None,
    image_rgb=None,  # NEW: pre-decoded RGB array
) -> PipelineResult:
    # If image_rgb provided, skip decode and pass to preprocessing
    # Otherwise decode from image_data (backward compat)
```

The preprocessing pipeline (`run_pipeline()`) would need to accept an optional pre-decoded image too, or `detect_bib_numbers` passes it through.

### Modified: `pipeline/single_photo.py`

Pass the already-decoded image:

```python
bib_result = detect_fn(reader, image_data, artifact_dir=artifact_dir, image_rgb=image_rgb)
```

## Test-first approach

```python
def test_detect_bib_numbers_accepts_preloaded_image():
    """detect_bib_numbers() produces same result with pre-decoded image."""
```

Mark as `@pytest.mark.slow` (needs EasyOCR).

## Acceptance criteria

- [ ] `detect_bib_numbers()` accepts optional `image_rgb` parameter
- [ ] `run_single_photo()` passes decoded image to bib detection
- [ ] Image decoded exactly once per photo
- [ ] Production callers unaffected (still pass bytes without image_rgb)
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: parameter addition, pipeline plumbing
- **Out of scope**: preprocessing changes, detection behavior changes
