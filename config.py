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
CLAHE_ENABLED = True
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_SIZE = (8, 8)
CLAHE_DYNAMIC_RANGE_THRESHOLD = 60.0
CLAHE_PERCENTILES = (5.0, 95.0)

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
# FACE RECOGNITION
# =============================================================================

# Face backend selection (swappable via config)
FACE_BACKEND = "opencv_dnn_ssd"

# OpenCV Haar cascade detection parameters
FACE_DETECTION_SCALE_FACTOR = 1.1
FACE_DETECTION_MIN_NEIGHBORS = 8
FACE_DETECTION_MIN_SIZE = (60, 60)
FACE_DETECTION_EYE_CASCADE = "haarcascade_eye.xml"
FACE_DETECTION_REQUIRE_EYES = 1
FACE_DETECTION_EYE_MIN_NEIGHBORS = 3
FACE_DETECTION_EYE_MIN_SIZE = (15, 15)

FACE_DNN_PROTO_PATH = "faces/models/opencv_dnn_ssd/deploy.prototxt"
FACE_DNN_MODEL_PATH = "faces/models/opencv_dnn_ssd/res10_300x300_ssd_iter_140000.caffemodel"
FACE_DNN_INPUT_SIZE = (300, 300)
FACE_DNN_MEAN = (104.0, 177.0, 123.0)
FACE_DNN_SCALE = 1.0
FACE_DNN_SWAP_RB = False
FACE_DNN_CONFIDENCE_MIN = 0.5
FACE_DNN_NMS_IOU = 0.4

# Simple embedding size (square grayscale image size)
FACE_EMBEDDING_SIZE = 32

# Face snippet padding ratio (fraction of bbox size)
FACE_SNIPPET_PADDING_RATIO = 0.10

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
