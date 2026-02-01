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
config = PreprocessConfig(target_width=1280)

# Run the pipeline
result = run_pipeline(image, config)

# Access results
result.original          # Original image (copy)
result.grayscale         # Grayscale at original size
result.resized           # RGB resized to target width
result.resized_grayscale # Grayscale resized
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

### Recommended Settings

- **target_width=1280**: Good balance of detail and speed
- **target_width=1600**: More detail, slower processing
- **target_width=None**: Skip resizing (for already small images)

## Future Extensions

The preprocessing module is designed to be extended with:
- Contrast enhancement (CLAHE)
- Noise reduction
- Perspective correction
- Bib region isolation

Each new operation will follow the same pure function design.
