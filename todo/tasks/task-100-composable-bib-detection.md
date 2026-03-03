# Task 100: Composable bib detection pipeline

Independent of other tasks.

## Goal

Make the bib detection pipeline composable across three independent axes — image prep, candidate finding, and OCR strategy — so each can be swapped independently via config without deleting code. Enable A/B benchmarking of any combination.

## Background

Investigating a benchmark regression after task-087 (remove full-image OCR fallback), we discovered three problems:

1. **Bug**: `_build_bib_trace` used the candidate bbox (white region) instead of the OCR detection bbox (tight around digits) → IoU scoring failed. Fixed in this session.
2. **Bug**: `WHITE_THRESHOLD=200` was too aggressive, clipping bib edges. Lowered to 180.
3. **Design flaw**: Grayscale thresholding for white-region detection can't distinguish "white" from "bright" — skin, light clothing, and reflective surfaces produce false candidates while fragmenting actual bibs. HSV-based detection (high V, low S) eliminates this class of error.

We tested three approaches in a single session, each overwriting the previous:
- White-region crops on grayscale (72.6% bib F1, ~200s)
- Full-image OCR, no candidates (88.6% bib F1, ~815s — 4x slower)
- HSV candidate detection (not yet tested — session ran out of discipline)

The trial-and-error approach made it impossible to compare or revert. We need a composable architecture where implementations coexist and a benchmark run specifies which combination to use.

## Context

- `detection/detector.py` — `detect_bib_numbers()`: orchestrates preprocessing → candidates → OCR → filtering
- `detection/regions.py` — `find_bib_candidates()`: white-region detection using grayscale threshold
- `config.py` — detection constants (`WHITE_THRESHOLD`, `MIN_CONTOUR_AREA`, etc.)
- `preprocessing/steps.py` — existing composable `PreprocessStep` → `Pipeline` pattern (model to follow)
- `preprocessing/config.py` — `PreprocessConfig` frozen dataclass pattern
- `pipeline/single_photo.py` — `run_single_photo()`: single entry point, already has `detect_fn` injection
- `benchmarking/runner.py` — `PipelineConfig` snapshot in `RunMetadata`, threading config through

### Key findings from this session

- CLAHE is declined on every photo in the dataset (dynamic range always > 60) — it's a no-op
- Full-image OCR proves EasyOCR on grayscale works fine for reading text. The problem is candidate *finding*, not OCR
- HSV thresholding (V > 180, S < 50) eliminated skin/clothing false positives in manual tests on two photos (02368141, 006c6313)
- OCR crop regions that clip the top of digits cause truncated reads (e.g., "231" → "L24", "326" → "26")

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| How many composable axes? | Three independent axes: (1) image prep, (2) candidate finding, (3) OCR strategy |
| How to select? | One enum per axis, bundled in a `BibPipelineConfig` dataclass |
| Can they be mixed freely? | Yes. E.g. HSV candidates + full-image OCR, or grayscale candidates + crop OCR |
| Delete old implementations? | No. All implementations coexist, selected by config |
| HSV: what image for candidate finding? | Color image resized to OCR dimensions (coordinates must align) |

### Three composable axes

**Axis 1 — Image prep** (`ImagePrepMethod`):
- `GRAYSCALE`: current — RGB → grayscale → optional CLAHE → resize (passed to both candidate finder and OCR)
- `COLOR`: RGB → resize (keep color for candidate finding; convert to grayscale only for OCR if needed)

**Axis 2 — Candidate finding** (`CandidateFindMethod`):
- `GRAYSCALE_THRESHOLD`: current — `cv2.threshold(gray, WHITE_THRESHOLD)` → contours
- `HSV_WHITE`: new — threshold on HSV (high V + low S) → contours. Requires color input.
- `NONE`: no candidate finding (for use with full-image OCR)

**Axis 3 — OCR strategy** (`OCRMethod`):
- `CROP`: current — run `reader.readtext()` on each candidate crop
- `FULL_IMAGE`: run `reader.readtext()` on the entire image, filter for valid bibs

Valid combinations include:
- `COLOR` + `HSV_WHITE` + `CROP` — the fast targeted approach we want to test
- `GRAYSCALE` + `GRAYSCALE_THRESHOLD` + `CROP` — current behavior
- `GRAYSCALE` + `NONE` + `FULL_IMAGE` — the 88.6% F1 run we measured
- `COLOR` + `NONE` + `FULL_IMAGE` — does color help full-image OCR?
- `GRAYSCALE` + `GRAYSCALE_THRESHOLD` + `FULL_IMAGE` — old fallback behavior (candidates for diagnostics, OCR on full image)

## Changes

### Modified: `config.py`

Add enums for the three axes, a config dataclass, and HSV parameter:

```python
from enum import Enum

class ImagePrepMethod(str, Enum):
    GRAYSCALE = "grayscale"  # RGB → grayscale → CLAHE → resize
    COLOR = "color"          # RGB → resize (keep color)

class CandidateFindMethod(str, Enum):
    GRAYSCALE_THRESHOLD = "grayscale_threshold"  # brightness threshold on grayscale
    HSV_WHITE = "hsv_white"                      # V > threshold AND S < max_saturation
    NONE = "none"                                # no candidate finding

class OCRMethod(str, Enum):
    CROP = "crop"            # OCR per candidate crop
    FULL_IMAGE = "full_image" # OCR on entire image

@dataclass(frozen=True)
class BibPipelineConfig:
    image_prep: ImagePrepMethod = ImagePrepMethod.GRAYSCALE
    candidate_find: CandidateFindMethod = CandidateFindMethod.GRAYSCALE_THRESHOLD
    ocr_method: OCRMethod = OCRMethod.CROP

WHITE_MAX_SATURATION = 50  # HSV saturation ceiling (0-255)
```

### Modified: `detection/regions.py`

Add `method` parameter to `find_bib_candidates()`. Branch on method:

- `GRAYSCALE_THRESHOLD`: current code, unchanged
- `HSV_WHITE`: `cv2.cvtColor(image, COLOR_RGB2HSV)`, threshold `V > WHITE_THRESHOLD` AND `S < WHITE_MAX_SATURATION`, `findContours`. Same validation filters after. Requires RGB input.
- `NONE`: return empty list

Brightness metrics for traces still computed on grayscale (backward compat).

### Modified: `detection/detector.py`

Accept `BibPipelineConfig` and branch on each axis:

- **Image prep axis**: determines what image is prepared (color-resized vs grayscale-preprocessed)
- **Candidate finding axis**: determines how candidates are found (or skipped)
- **OCR axis**: determines whether OCR runs on crops or the full image

When `ocr_method=CROP` and no candidates are found, there's nothing to OCR (no detections). When `ocr_method=FULL_IMAGE`, candidates are still found for diagnostics but OCR runs on the full image.

### Modified: `pipeline/single_photo.py`

Thread `BibPipelineConfig` through `run_single_photo()` → `detect_bib_numbers()`.

### Modified: `benchmarking/runner.py`

Thread `BibPipelineConfig` through `_run_detection_loop()` → `run_single_photo()`. Snapshot in `PipelineConfig` / `RunMetadata`.

### Modified: `benchmarking/cli/`

Add CLI flags for each axis (optional, defaults from `BibPipelineConfig`):
- `--image-prep grayscale|color`
- `--candidate-find grayscale_threshold|hsv_white|none`
- `--ocr-method crop|full_image`

### API design note

`BibPipelineConfig` is the primary API. All composition happens through it — in tests, in debugging, in production code. CLI flags are a thin wrapper that constructs the config.

```python
# In tests / debugging
config = BibPipelineConfig(
    image_prep=ImagePrepMethod.COLOR,
    candidate_find=CandidateFindMethod.HSV_WHITE,
    ocr_method=OCRMethod.CROP,
)
result = detect_bib_numbers(reader, image_data, bib_config=config)

# In run_single_photo
sp_result = run_single_photo(image_data, reader=reader, bib_config=config)

# In benchmark runner
run_benchmark(bib_config=config, ...)

# Via CLI (constructs the config)
bnr benchmark run --image-prep color --candidate-find hsv_white --ocr-method crop
```

The default `BibPipelineConfig()` (no arguments) produces current behavior. Every function that currently hardcodes detection choices should accept an optional `bib_config` parameter instead.

## Tests

Add `tests/test_candidate_methods.py`:

- `test_grayscale_method_finds_white_region()` — synthetic white rect on dark background
- `test_hsv_method_finds_white_region()` — same synthetic image, RGB input
- `test_hsv_method_rejects_bright_skin_tone()` — bright warm-colored region (high V, high S) → not found as candidate
- `test_full_image_returns_no_candidates()` — returns empty list

Extend `tests/test_pipeline.py`:

- `test_run_single_photo_accepts_candidate_method()` — verify parameter threading

## Verification

```bash
# Unit tests
venv/bin/python -m pytest tests/test_candidate_methods.py tests/test_pipeline.py -v

# Full suite
venv/bin/python -m pytest

# Benchmark comparison — key combinations on jeugd-1
# Current behavior (baseline)
venv/bin/python bnr.py benchmark run -s full -S jeugd-1 --image-prep grayscale --candidate-find grayscale_threshold --ocr-method crop
# HSV candidate finding (the main thing we want to test)
venv/bin/python bnr.py benchmark run -s full -S jeugd-1 --image-prep color --candidate-find hsv_white --ocr-method crop
# Full-image OCR (accuracy upper bound, slower)
venv/bin/python bnr.py benchmark run -s full -S jeugd-1 --image-prep grayscale --candidate-find none --ocr-method full_image
```

## Pitfalls

- HSV candidate finder needs RGB input. If passed grayscale, fall back to grayscale method with a warning.
- Color resize must produce the exact same dimensions as `ocr_image` so candidate bbox coordinates align with OCR crops.
- `FULL_IMAGE` detections have `source_candidate=None` — `_build_bib_trace` already handles this via the fallback path (lines 111-124 in `pipeline/single_photo.py`).
- The detection bbox fix (using OCR bbox instead of candidate bbox for accepted traces) must stay — it's critical for IoU scoring.

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] New tests pass for each candidate-finding method
- [ ] Default config (`GRAYSCALE` + `GRAYSCALE_THRESHOLD` + `CROP`) produces identical results to current code
- [ ] All three axes are independently configurable via CLI flags
- [ ] Run metadata includes the full `BibPipelineConfig` used
- [ ] No code from any implementation is deleted — all options coexist
- [ ] At least three benchmark runs compared (grayscale-crop, hsv-crop, full-image)

## Scope boundaries

- **In scope**: three-axis composability, `BibPipelineConfig`, CLI flags, benchmark comparison
- **Out of scope**: tuning EasyOCR settings (allowlist, thresholds), tuning HSV parameters, removing CLAHE code
- **Do not** delete any implementation — all options must remain available
