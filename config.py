"""Central configuration for bib number detection.

All tunable parameters are defined here with descriptive names.
These values can be adjusted to fine-tune detection performance.

See DETECTION.md for documentation on how these values affect detection.
"""

# =============================================================================
# IMAGE PREPROCESSING
# =============================================================================

# Target width for resizing images before OCR (balances speed vs accuracy)
TARGET_WIDTH = 1280

# Minimum allowed target width (too small loses detail)
MIN_TARGET_WIDTH = 256

# Maximum allowed target width (too large is slow with diminishing returns)
MAX_TARGET_WIDTH = 4096

# CLAHE (contrast enhancement) defaults
CLAHE_ENABLED = False
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_SIZE = (8, 8)
CLAHE_DYNAMIC_RANGE_THRESHOLD = 60.0
CLAHE_PERCENTILES = (5.0, 95.0)

# =============================================================================
# URL GENERATION (Google Photos)
# =============================================================================

# Width parameter for full-resolution photo URLs
PHOTO_URL_WIDTH = 2048

# Width parameter for thumbnail URLs
THUMBNAIL_URL_WIDTH = 400

# =============================================================================
# WHITE REGION DETECTION
# =============================================================================

# Minimum contour area in pixels to consider as a candidate bib region
MIN_CONTOUR_AREA = 1000

# Threshold for binary thresholding to find white regions (0-255)
# Higher = stricter white detection
WHITE_THRESHOLD = 200

# Aspect ratio range for candidate regions (width/height)
# Bibs are roughly square, so we allow 0.5 to 4.0
MIN_ASPECT_RATIO = 0.5
MAX_ASPECT_RATIO = 4.0

# Region size relative to image area
# Too small = noise, too large = not a bib
MIN_RELATIVE_AREA = 0.001  # 0.1% of image
MAX_RELATIVE_AREA = 0.3    # 30% of image

# Padding ratio around detected regions (fraction of min(width, height))
REGION_PADDING_RATIO = 0.1

# =============================================================================
# BRIGHTNESS VALIDATION
# =============================================================================

# Brightness thresholds to filter false positives (dark regions with light text)
# Real bibs are predominantly white (median ~150-165, mean ~135-140)
# False positives (e.g., Adidas text on black) have median ~20-30, mean ~60
MEDIAN_BRIGHTNESS_THRESHOLD = 120
MEAN_BRIGHTNESS_THRESHOLD = 100

# =============================================================================
# OCR CONFIDENCE THRESHOLDS
# =============================================================================

# Confidence threshold for OCR on white regions (lower because context helps)
WHITE_REGION_CONFIDENCE_THRESHOLD = 0.4

# Confidence threshold for full-image OCR fallback (higher to reduce noise)
FULL_IMAGE_CONFIDENCE_THRESHOLD = 0.5

# =============================================================================
# DETECTION FILTERING
# =============================================================================

# Minimum ratio of detection area to white region area
# A bib number should occupy at least 10% of the bib
MIN_DETECTION_AREA_RATIO = 0.10

# IoU threshold for considering two boxes as overlapping
IOU_OVERLAP_THRESHOLD = 0.3

# Coverage overlap ratio threshold (how much of smaller box is covered)
COVERAGE_OVERLAP_THRESHOLD = 0.7

# Confidence ratio threshold for preferring shorter bib number over longer
# When "600" overlaps "6600", keep "600" only if its confidence is 1.5x higher
SUBSTRING_CONFIDENCE_RATIO = 1.5

# =============================================================================
# SNIPPET GENERATION
# =============================================================================

# Padding ratio around bounding box when saving snippets (fraction of bbox size)
SNIPPET_PADDING_RATIO = 0.15

# =============================================================================
# BIB NUMBER VALIDATION
# =============================================================================

# Valid bib number range
MIN_BIB_NUMBER = 1
MAX_BIB_NUMBER = 9999

# =============================================================================
# BENCHMARKING
# =============================================================================

# Probability that a new photo is assigned to the "iteration" split
# (vs "full" split) when labeling for the first time
ITERATION_SPLIT_PROBABILITY = 0.5

# Tolerance threshold for regression detection (as a fraction, e.g., 0.005 = 0.5%)
# A drop in precision or recall smaller than this is not considered a regression
BENCHMARK_REGRESSION_TOLERANCE = 0.005
