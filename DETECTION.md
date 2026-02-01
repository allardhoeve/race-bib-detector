# Bib Number Detection

This document describes the bib number detection pipeline.

## Overview

The detection module identifies race bib numbers in photos using:
1. **White region detection** - Find candidate areas that look like bibs
2. **OCR** - Extract text from candidate regions
3. **Validation** - Filter for valid bib number patterns
4. **Deduplication** - Remove overlapping/duplicate detections

## Pipeline Stages

### Stage 1: White Region Detection

Bibs are typically white rectangles. We find candidate regions by:

```python
from detection import find_white_regions

regions = find_white_regions(image_array)
# Returns: [(x, y, w, h), ...]
```

Filtering criteria:
- Minimum area (1000 px²)
- Aspect ratio 0.5 to 4.0 (bibs are roughly square)
- Relative size 0.1% to 30% of image

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
- If one text is a substring of another ("6" vs "620"), keep the longer one
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
from detection import detect_bib_numbers

bibs, grayscale = detect_bib_numbers(reader, image_data, preprocess_config)

for bib in bibs:
    print(f"Bib {bib['bib_number']}: {bib['confidence']:.0%}")
    print(f"  Location: {bib['bbox']}")
```

Returns:
- List of detection dicts with `bib_number`, `confidence`, `bbox`
- Grayscale image used for OCR (for visualization)

## Configuration

Detection uses preprocessing configuration:

```python
from preprocessing import PreprocessConfig

config = PreprocessConfig(target_width=1280)
bibs, gray = detect_bib_numbers(reader, image_data, config)
```

Resizing to a fixed width ensures consistent kernel behavior for region detection.

## Confidence Thresholds

| Context | Threshold |
|---------|-----------|
| White region OCR | 0.4 |
| Full image OCR | 0.5 |
| Size ratio | 0.10 |
| IoU overlap | 0.3 |
| Coverage overlap | 0.7 |

Higher thresholds for full-image scan reduce false positives where we lack the white region context.
