# Task 078: Share image decode between bib and face detection

Part of the tuning series (071–077). Small optimization.

## Goal

Decode each photo's image once and pass the decoded array to both `_run_bib_detection()` and `_run_face_detection()`, eliminating redundant decodes.

## Background

Currently `_run_bib_detection()` receives raw `image_data: bytes` and calls `detect_bib_numbers()` which decodes internally. `_run_face_detection()` also receives `image_data: bytes` and decodes with `cv2.imdecode()`. Same image decoded twice per photo.

After task-074 moves embedding into `_run_face_detection()`, the image is still decoded once there. But bib detection decodes it separately inside `detect_bib_numbers()`.

## Changes

In `_run_detection_loop()`, decode the image once before calling either detection function. Pass the decoded RGB array (and dimensions) to both.

This requires `detect_bib_numbers()` to accept an optional pre-decoded image, falling back to decoding `image_data` if not provided (backward compat with production callers).

## Test-first approach

```python
def test_detect_bib_numbers_accepts_preloaded_image():
    """detect_bib_numbers() works with pre-decoded image array."""

def test_run_face_detection_accepts_preloaded_image():
    """_run_face_detection() works with pre-decoded image array."""
```

## Acceptance criteria

- [ ] Image decoded once per photo in the detection loop
- [ ] Both detection functions accept optional pre-decoded image
- [ ] Production callers unaffected (still pass bytes)
- [ ] TDD tests pass
- [ ] All existing tests pass
