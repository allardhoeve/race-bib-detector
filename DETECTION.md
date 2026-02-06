# Bib Number Detection

This document describes the bib number detection pipeline.

For facial recognition planning and clustering details, see
`todo_facial_recognition.md`.

## Overview

The detection module identifies race bib numbers in photos using:
1. **White region detection** - Find candidate areas that look like bibs
2. **OCR** - Extract text from candidate regions
3. **Validation** - Filter for valid bib number patterns
4. **Deduplication** - Remove overlapping/duplicate detections

## Pipeline Stages

### Stage 1: Bib Candidate Detection

Bibs are typically white rectangles. We find candidate regions using `find_bib_candidates()`:

```python
from detection import find_bib_candidates, BibCandidate

candidates = find_bib_candidates(image_array)
# Returns: list[BibCandidate]

for candidate in candidates:
    print(f"Region at ({candidate.x}, {candidate.y}) size {candidate.w}x{candidate.h}")
    print(f"  Brightness: median={candidate.median_brightness}, mean={candidate.mean_brightness}")
    print(f"  Aspect ratio: {candidate.aspect_ratio:.2f}")

    # Extract the region for OCR
    region = candidate.extract_region(image_array)
```

To debug why candidates are rejected, use `include_rejected=True`:

```python
all_candidates = find_bib_candidates(image_array, include_rejected=True)
for c in all_candidates:
    if not c.passed:
        print(f"Rejected: {c.rejection_reason}")
```

Filtering criteria:
- Minimum area (1000 px²)
- Aspect ratio 0.5 to 4.0 (bibs are roughly square)
- Relative size 0.1% to 30% of image
- **Brightness validation**: median > 120, mean > 100

#### Brightness Validation

The brightness check prevents false positives from light text on dark backgrounds (e.g., "Adidas" logo on black pants being misread as "8"). Real bibs are predominantly white:

| Region Type | Median Brightness | Mean Brightness |
|-------------|-------------------|-----------------|
| Real bib | ~150-165 | ~135-140 |
| False positive (text on dark) | ~20-30 | ~60 |

Thresholds (median > 120, mean > 100) are set conservatively below real bibs but well above false positives.

### Stage 2: OCR

Each white region is processed with EasyOCR:

```python
results = reader.readtext(region)
# Returns: [(bbox, text, confidence), ...]
```

A fallback full-image scan catches bibs missed by region detection.

### Stage 3: Validation

Detected text is validated as a bib number:

```python
from detection import is_valid_bib_number

is_valid_bib_number("353")   # True
is_valid_bib_number("0123")  # False (leading zero)
is_valid_bib_number("abc")   # False (non-numeric)
is_valid_bib_number("10000") # False (> 9999)
```

Valid bibs are 1-4 digits, no leading zeros, range 1-9999.

### Stage 4: Filtering

Two filtering passes remove false positives:

**Size filtering**: Removes tiny detections relative to the white region:

```python
from detection import filter_small_detections

filtered = filter_small_detections(detections, region_area, min_ratio=0.10)
```

A bib number should occupy at least 10% of the bib region.

**Overlap filtering**: Removes duplicate detections:

```python
from detection import filter_overlapping_detections

filtered = filter_overlapping_detections(detections)
```

When boxes overlap:
- If one text is a substring of another ("6" vs "620"):
  - Keep the longer one, UNLESS the shorter has significantly higher confidence (1.5x threshold)
  - This handles cases like "600" (conf=1.0) vs "6600" (conf=0.5) where partial text was misread
- Otherwise, keep the one with more digits
- If same digit count, keep higher confidence

## Bounding Box Utilities

The `bbox` module provides geometry functions:

```python
from detection import bbox_area, bbox_iou, bbox_overlap_ratio

# Calculate area of quadrilateral
area = bbox_area([[0,0], [10,0], [10,10], [0,10]])  # 100.0

# Intersection over Union
iou = bbox_iou(bbox1, bbox2)  # 0.0 to 1.0

# How much of smaller box is covered
overlap = bbox_overlap_ratio(bbox1, bbox2)  # 0.0 to 1.0
```

## Main Entry Point

The `detect_bib_numbers` function orchestrates the full pipeline:

```python
from detection import detect_bib_numbers, DetectionResult

result = detect_bib_numbers(reader, image_data, preprocess_config)

for det in result.detections:
    print(f"Bib {det.bib_number}: {det.confidence:.0%}")
    print(f"  Location: {det.bbox}")

# Access metadata
print(f"Original size: {result.original_dimensions}")
print(f"OCR size: {result.ocr_dimensions}")
print(f"Scale factor: {result.scale_factor}")

# Get detections at OCR resolution for visualization
scaled_detections = result.detections_at_ocr_scale()
```

Returns a `DetectionResult` containing:
- `detections`: List of `Detection` objects (see below)
- `ocr_grayscale`: Grayscale image used for OCR (for visualization)
- `original_dimensions`: (width, height) of original image
- `ocr_dimensions`: (width, height) of OCR image
- `scale_factor`: Ratio for coordinate mapping

## Detection Lineage

Each `Detection` tracks its origin for debugging and transparency:

```python
for det in result.detections:
    print(f"Bib {det.bib_number}: source={det.source}")

    if det.source == "white_region" and det.source_candidate:
        # Trace back to the candidate region
        candidate = det.source_candidate
        print(f"  From candidate at ({candidate.x}, {candidate.y})")
        print(f"  Candidate brightness: {candidate.median_brightness}")
    elif det.source == "full_image":
        print("  Found via full-image fallback scan")
```

Detection attributes:
- `bib_number`: The detected number (e.g., "123")
- `confidence`: OCR confidence (0.0 to 1.0)
- `bbox`: Bounding box as 4 [x,y] points
- `source`: Detection method (`"white_region"` or `"full_image"`)
- `source_candidate`: The `BibCandidate` this came from (None for full_image)

## Configuration

Detection uses preprocessing configuration:

```python
from preprocessing import PreprocessConfig

config = PreprocessConfig(target_width=1280)
result = detect_bib_numbers(reader, image_data, config)
```

Resizing to a fixed width ensures consistent kernel behavior for region detection.

## Confidence Thresholds

| Context | Threshold | Config Variable |
|---------|-----------|-----------------|
| White region OCR | 0.4 | `WHITE_REGION_CONFIDENCE_THRESHOLD` |
| Full image OCR | 0.5 | `FULL_IMAGE_CONFIDENCE_THRESHOLD` |
| Size ratio | 0.10 | `MIN_DETECTION_AREA_RATIO` |
| IoU overlap | 0.3 | `IOU_OVERLAP_THRESHOLD` |
| Coverage overlap | 0.7 | `COVERAGE_OVERLAP_THRESHOLD` |

Higher thresholds for full-image scan reduce false positives where we lack the white region context.

All configurable values are defined in `config.py` for easy tuning.
