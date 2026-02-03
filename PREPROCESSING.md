# Image Preprocessing

This document describes the image preprocessing pipeline used before OCR detection.

## Philosophy

The preprocessing module is designed around these core principles:

### 1. Pure Functions

Every operation follows the pattern `(input) -> output` with no side effects:

```python
# Good: Pure function returns new array
gray = to_grayscale(rgb_image)

# The original is never modified
assert rgb_image is not gray
```

This design makes functions:
- Easy to test in isolation
- Predictable and reproducible
- Safe to compose in pipelines

### 2. Early Validation

Parameters are validated at configuration time, not during processing:

```python
config = PreprocessConfig(target_width=50)  # Creates config
config.validate()  # Raises: "target_width=50 is too small for reliable OCR"
```

Error messages are actionable and explain what's wrong and how to fix it.

### 3. Type Normalization

Consistent types throughout the pipeline:
- **Grayscale images**: `numpy.uint8`, 2D array `(height, width)`
- **Color images**: `numpy.uint8`, 3D array `(height, width, 3)`
- **Binary images**: `numpy.uint8`, values 0 or 255

## Pipeline Stages

### Stage 1: Normalization

#### Grayscale Conversion

```python
from preprocessing import to_grayscale

gray = to_grayscale(rgb_image)
# Input: (H, W, 3) RGB uint8
# Output: (H, W) grayscale uint8
```

Handles various input formats:
- RGB (3 channels): Standard conversion
- RGBA (4 channels): Drops alpha, then converts
- Already grayscale: Returns a copy

#### Contrast Enhancement (CLAHE)

CLAHE is optional and only applied when the grayscale image has low global
contrast. The default heuristic computes the 5th and 95th percentiles and
applies CLAHE when `p95 - p5` falls below the configured threshold.

Why apply CLAHE conditionally?
- Avoids amplifying noise in already high-contrast images
- Keeps processing consistent without a manual toggle

#### Resize to Fixed Width

```python
from preprocessing import resize_to_width

resized, scale_factor = resize_to_width(image, target_width=1280)
```

Why a fixed width?
- Morphological kernels (e.g., for noise removal) have consistent meaning
- OCR models perform more consistently at similar scales
- Processing time is predictable

The `scale_factor` is returned for mapping detections back to original coordinates.

### Using the Full Pipeline

```python
from preprocessing import run_pipeline, PreprocessConfig

# Create configuration
config = PreprocessConfig(target_width=1280, clahe_enabled=True)

# Run the pipeline
result = run_pipeline(image, config)

# Access results
result.original          # Original image (copy)
result.processed         # Grayscale, CLAHE (if applied), resized (if enabled)
result.scale_factor      # For coordinate mapping
```

### Mapping Coordinates Back

When you detect something in the resized image, map coordinates back:

```python
# Detection in resized image
bbox_resized = [[10, 10], [50, 10], [50, 30], [10, 30]]

# Map to original coordinates
bbox_original = result.map_bbox_to_original(bbox_resized)
```

## Configuration Reference

`PreprocessConfig` parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_width` | 1280 | Width to resize to (None to skip) |
| `grayscale_dtype` | uint8 | Dtype for grayscale images |
| `binary_dtype` | uint8 | Dtype for binary images |
| `clahe_enabled` | False | Enable CLAHE contrast enhancement |
| `clahe_clip_limit` | 2.0 | CLAHE clip limit |
| `clahe_tile_size` | (8, 8) | CLAHE tile grid size |
| `clahe_dynamic_range_threshold` | 60.0 | Apply CLAHE when `p95 - p5` is below this |
| `clahe_percentiles` | (5.0, 95.0) | Percentiles used for dynamic range |

### Recommended Settings

- **target_width=1280**: Good balance of detail and speed
- **target_width=1600**: More detail, slower processing
- **target_width=None**: Skip resizing (for already small images)

## Future Extensions

The preprocessing module is designed to be extended with:
- Advanced contrast heuristics
- Noise reduction
- Perspective correction
- Bib region isolation

Each new operation will follow the same pure function design.

### Optional TODOs: Smarter CLAHE Triggers

- TODO: Tile-based contrast check (apply CLAHE if most tiles are low-contrast)
- TODO: Use local dynamic range within candidate bib regions (post region proposal)
- TODO: Use gradient magnitude statistics as a contrast proxy
