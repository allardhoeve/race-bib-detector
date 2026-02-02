"""Tests for bib number detection and database operations."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import db
from detection import detect_bib_numbers, is_valid_bib_number

SAMPLES_DIR = Path(__file__).parent / "samples"


@pytest.fixture(scope="module")
def ocr_reader():
    """Initialize EasyOCR reader once for all tests."""
    import easyocr
    return easyocr.Reader(["en"], gpu=False)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_path = Path(tempfile.mktemp(suffix=".db"))

    # Create connection and initialize schema manually
    conn = sqlite3.connect(temp_path)
    conn.row_factory = sqlite3.Row
    db.init_database(conn)

    yield conn

    conn.close()
    temp_path.unlink(missing_ok=True)


class TestBibValidation:
    """Tests for bib number validation."""

    def test_valid_bib_numbers(self):
        """Test that valid bib numbers are accepted."""
        assert is_valid_bib_number("1")
        assert is_valid_bib_number("42")
        assert is_valid_bib_number("353")
        assert is_valid_bib_number("9999")
        assert is_valid_bib_number("622")

    def test_invalid_leading_zero(self):
        """Test that numbers with leading zeros are rejected."""
        assert not is_valid_bib_number("01")
        assert not is_valid_bib_number("05")
        assert not is_valid_bib_number("001")
        assert not is_valid_bib_number("0123")

    def test_invalid_zero(self):
        """Test that zero alone is rejected."""
        assert not is_valid_bib_number("0")

    def test_invalid_too_large(self):
        """Test that numbers > 9999 are rejected."""
        assert not is_valid_bib_number("10000")
        assert not is_valid_bib_number("99999")

    def test_invalid_non_numeric(self):
        """Test that non-numeric strings are rejected."""
        assert not is_valid_bib_number("abc")
        assert not is_valid_bib_number("12a")
        assert not is_valid_bib_number("")

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        assert is_valid_bib_number(" 42 ")
        assert is_valid_bib_number("4 2")  # spaces removed


class TestDetectionDataclass:
    """Tests for the Detection dataclass."""

    def test_detection_creation(self):
        """Test basic Detection creation."""
        from detection import Detection
        det = Detection(bib_number="123", confidence=0.95, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        assert det.bib_number == "123"
        assert det.confidence == 0.95
        assert det.bbox == [[0, 0], [10, 0], [10, 10], [0, 10]]

    def test_detection_scale_bbox(self):
        """Test Detection.scale_bbox returns new Detection with scaled bbox."""
        from detection import Detection
        det = Detection(bib_number="123", confidence=0.95, bbox=[[100, 100], [200, 100], [200, 200], [100, 200]])
        scaled = det.scale_bbox(0.5)

        # Original unchanged
        assert det.bbox == [[100, 100], [200, 100], [200, 200], [100, 200]]

        # Scaled Detection has new bbox
        assert scaled.bbox == [[50, 50], [100, 50], [100, 100], [50, 100]]
        assert scaled.bib_number == "123"
        assert scaled.confidence == 0.95

    def test_detection_to_dict(self):
        """Test Detection.to_dict for backwards compatibility."""
        from detection import Detection
        det = Detection(bib_number="456", confidence=0.8, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        d = det.to_dict()
        assert d == {"bib_number": "456", "confidence": 0.8, "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]], "source": "white_region"}

    def test_detection_from_dict(self):
        """Test Detection.from_dict for backwards compatibility."""
        from detection import Detection
        d = {"bib_number": "789", "confidence": 0.7, "bbox": [[5, 5], [15, 5], [15, 15], [5, 15]]}
        det = Detection.from_dict(d)
        assert det.bib_number == "789"
        assert det.confidence == 0.7
        assert det.bbox == [[5, 5], [15, 5], [15, 15], [5, 15]]
        # Default source when not in dict
        assert det.source == "white_region"

    def test_detection_from_dict_with_source(self):
        """Test Detection.from_dict preserves source field."""
        from detection import Detection
        d = {"bib_number": "789", "confidence": 0.7, "bbox": [[5, 5], [15, 5], [15, 15], [5, 15]], "source": "full_image"}
        det = Detection.from_dict(d)
        assert det.source == "full_image"

    def test_detection_default_source(self):
        """Test Detection defaults to white_region source."""
        from detection import Detection
        det = Detection(bib_number="123", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        assert det.source == "white_region"
        assert det.source_candidate is None

    def test_detection_with_source_candidate(self):
        """Test Detection can track its source BibCandidate."""
        from detection import Detection, BibCandidate
        candidate = BibCandidate(
            bbox=(100, 100, 50, 30),
            area=1500,
            aspect_ratio=1.67,
            median_brightness=200,
            mean_brightness=195,
            relative_area=0.05,
        )
        det = Detection(
            bib_number="456",
            confidence=0.85,
            bbox=[[110, 110], [140, 110], [140, 125], [110, 125]],
            source="white_region",
            source_candidate=candidate,
        )
        assert det.source_candidate is candidate
        assert det.source_candidate.bbox == (100, 100, 50, 30)

    def test_detection_scale_bbox_preserves_lineage(self):
        """Test that scale_bbox preserves source and source_candidate."""
        from detection import Detection, BibCandidate
        candidate = BibCandidate(
            bbox=(100, 100, 50, 30),
            area=1500,
            aspect_ratio=1.67,
            median_brightness=200,
            mean_brightness=195,
            relative_area=0.05,
        )
        det = Detection(
            bib_number="123",
            confidence=0.9,
            bbox=[[100, 100], [200, 100], [200, 200], [100, 200]],
            source="white_region",
            source_candidate=candidate,
        )
        scaled = det.scale_bbox(0.5)

        assert scaled.source == "white_region"
        assert scaled.source_candidate is candidate

    def test_detection_full_image_source(self):
        """Test Detection with full_image source."""
        from detection import Detection
        det = Detection(
            bib_number="789",
            confidence=0.75,
            bbox=[[0, 0], [50, 0], [50, 30], [0, 30]],
            source="full_image",
        )
        assert det.source == "full_image"
        assert det.source_candidate is None


class TestDetectionResult:
    """Tests for DetectionResult/PipelineResult dataclass."""

    def test_detection_result_creation(self):
        """Test creating a DetectionResult (PipelineResult)."""
        import numpy as np
        from detection import Detection, DetectionResult, BibCandidate

        candidate = BibCandidate(
            bbox=(0, 0, 100, 50),
            area=5000,
            aspect_ratio=2.0,
            median_brightness=180.0,
            mean_brightness=175.0,
            relative_area=0.02,
        )
        detections = [Detection(bib_number="123", confidence=0.9, bbox=[[0, 0], [100, 0], [100, 50], [0, 50]], source_candidate=candidate)]
        grayscale = np.zeros((480, 640), dtype=np.uint8)

        result = DetectionResult(
            detections=detections,
            all_candidates=[candidate],
            ocr_grayscale=grayscale,
            original_dimensions=(1280, 960),
            ocr_dimensions=(640, 480),
            scale_factor=2.0,
        )

        assert len(result.detections) == 1
        assert len(result.all_candidates) == 1
        assert result.original_dimensions == (1280, 960)
        assert result.ocr_dimensions == (640, 480)
        assert result.scale_factor == 2.0

    def test_ocr_scale_property(self):
        """Test that ocr_scale is inverse of scale_factor."""
        import numpy as np
        from detection import DetectionResult

        result = DetectionResult(
            detections=[],
            all_candidates=[],
            ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
            original_dimensions=(200, 200),
            ocr_dimensions=(100, 100),
            scale_factor=2.0,
        )

        assert result.ocr_scale == 0.5

    def test_detections_at_ocr_scale(self):
        """Test that detections_at_ocr_scale scales bboxes correctly."""
        import numpy as np
        from detection import Detection, DetectionResult

        # Detection in original coords (scale_factor=2.0 means original is 2x OCR)
        det = Detection(bib_number="123", confidence=0.9, bbox=[[100, 100], [200, 100], [200, 200], [100, 200]])

        result = DetectionResult(
            detections=[det],
            all_candidates=[],
            ocr_grayscale=np.zeros((480, 640), dtype=np.uint8),
            original_dimensions=(1280, 960),
            ocr_dimensions=(640, 480),
            scale_factor=2.0,
        )

        scaled = result.detections_at_ocr_scale()
        assert len(scaled) == 1
        # Original bbox at 100,100 -> 200,200 should become 50,50 -> 100,100 at OCR scale
        assert scaled[0].bbox == [[50, 50], [100, 50], [100, 100], [50, 100]]

    def test_passed_and_rejected_candidates(self):
        """Test passed_candidates and rejected_candidates properties."""
        import numpy as np
        from detection import DetectionResult, BibCandidate

        passed = BibCandidate(
            bbox=(0, 0, 100, 50),
            area=5000,
            aspect_ratio=2.0,
            median_brightness=180.0,
            mean_brightness=175.0,
            relative_area=0.02,
            passed=True,
        )
        rejected = BibCandidate.create_rejected(
            bbox=(200, 200, 20, 10),
            area=200,
            aspect_ratio=2.0,
            median_brightness=50.0,
            mean_brightness=45.0,
            relative_area=0.001,
            reason="too_small",
        )

        result = DetectionResult(
            detections=[],
            all_candidates=[passed, rejected],
            ocr_grayscale=np.zeros((480, 640), dtype=np.uint8),
            original_dimensions=(1280, 960),
            ocr_dimensions=(640, 480),
            scale_factor=2.0,
        )

        assert len(result.passed_candidates) == 1
        assert len(result.rejected_candidates) == 1
        assert result.passed_candidates[0] is passed
        assert result.rejected_candidates[0] is rejected


class TestBibCandidate:
    """Tests for BibCandidate dataclass."""

    def test_bib_candidate_creation(self):
        """Test creating a BibCandidate."""
        from detection import BibCandidate

        candidate = BibCandidate(
            bbox=(100, 200, 50, 60),
            area=3000,
            aspect_ratio=0.83,
            median_brightness=180.0,
            mean_brightness=175.0,
            relative_area=0.01,
            passed=True,
        )

        assert candidate.bbox == (100, 200, 50, 60)
        assert candidate.x == 100
        assert candidate.y == 200
        assert candidate.w == 50
        assert candidate.h == 60
        assert candidate.passed is True
        assert candidate.rejection_reason is None

    def test_bib_candidate_rejected(self):
        """Test creating a rejected BibCandidate."""
        from detection import BibCandidate

        candidate = BibCandidate.create_rejected(
            bbox=(10, 20, 30, 40),
            area=1200,
            aspect_ratio=0.75,
            median_brightness=80.0,
            mean_brightness=85.0,
            relative_area=0.001,
            reason="brightness too low",
        )

        assert candidate.passed is False
        assert candidate.rejection_reason == "brightness too low"

    def test_bib_candidate_to_xywh(self):
        """Test to_xywh method."""
        from detection import BibCandidate

        candidate = BibCandidate(
            bbox=(10, 20, 30, 40),
            area=1200,
            aspect_ratio=0.75,
            median_brightness=150.0,
            mean_brightness=145.0,
            relative_area=0.01,
        )

        assert candidate.to_xywh() == (10, 20, 30, 40)

    def test_bib_candidate_extract_region(self):
        """Test extract_region method."""
        import numpy as np
        from detection import BibCandidate

        # Create a test image
        image = np.zeros((100, 100), dtype=np.uint8)
        image[20:40, 10:50] = 255  # White rectangle

        candidate = BibCandidate(
            bbox=(10, 20, 40, 20),
            area=800,
            aspect_ratio=2.0,
            median_brightness=255.0,
            mean_brightness=255.0,
            relative_area=0.008,
        )

        region = candidate.extract_region(image)
        assert region.shape == (20, 40)
        assert np.all(region == 255)


class TestBboxScaling:
    """Tests for bounding box scaling utilities."""

    def test_scale_bbox(self):
        """Test that scale_bbox scales coordinates correctly."""
        from detection import scale_bbox
        bbox = [[100, 200], [300, 200], [300, 400], [100, 400]]
        scaled = scale_bbox(bbox, 0.5)
        assert scaled == [[50, 100], [150, 100], [150, 200], [50, 200]]

    def test_scale_bbox_factor_greater_than_one(self):
        """Test scaling up with factor > 1."""
        from detection import scale_bbox
        bbox = [[10, 20], [30, 20], [30, 40], [10, 40]]
        scaled = scale_bbox(bbox, 2.0)
        assert scaled == [[20, 40], [60, 40], [60, 80], [20, 80]]

    def test_scale_bboxes(self):
        """Test that scale_bboxes scales a list of bounding boxes."""
        from detection import scale_bboxes
        bboxes = [
            [[100, 100], [200, 100], [200, 200], [100, 200]],
            [[300, 300], [400, 300], [400, 400], [300, 400]],
        ]
        scaled = scale_bboxes(bboxes, 0.5)
        assert scaled[0] == [[50, 50], [100, 50], [100, 100], [50, 100]]
        assert scaled[1] == [[150, 150], [200, 150], [200, 200], [150, 200]]

    def test_scale_bbox_does_not_mutate_original(self):
        """Test that scale_bbox returns a new list."""
        from detection import scale_bbox
        original = [[100, 100], [200, 100], [200, 200], [100, 200]]
        scaled = scale_bbox(original, 0.5)
        # Original should be unchanged
        assert original == [[100, 100], [200, 100], [200, 200], [100, 200]]
        # Scaled should be different
        assert scaled == [[50, 50], [100, 50], [100, 100], [50, 100]]


class TestOverlapFiltering:
    """Tests for overlapping detection filtering."""

    def test_choose_substring_keeps_longer(self):
        """When one bib is substring of another, keep the longer one."""
        from detection import Detection
        from detection.filtering import choose_detection_to_remove
        det1 = Detection(bib_number="6", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        det2 = Detection(bib_number="620", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        # bib1 "6" is substring of "620", should remove det1 (idx 0)
        assert choose_detection_to_remove(det1, det2, 0, 1) == 0

    def test_choose_substring_keeps_shorter_if_much_higher_confidence(self):
        """Keep shorter if it has much higher confidence than longer."""
        from detection import Detection
        from detection.filtering import choose_detection_to_remove
        det1 = Detection(bib_number="6", confidence=0.95, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        det2 = Detection(bib_number="620", confidence=0.5, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        # "6" has much higher confidence, should remove det2 (idx 1)
        assert choose_detection_to_remove(det1, det2, 0, 1) == 1

    def test_choose_more_digits_wins(self):
        """When no substring relation, prefer more digits."""
        from detection import Detection
        from detection.filtering import choose_detection_to_remove
        det1 = Detection(bib_number="12", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        det2 = Detection(bib_number="345", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        # det2 has more digits, remove det1
        assert choose_detection_to_remove(det1, det2, 0, 1) == 0

    def test_choose_same_length_higher_confidence_wins(self):
        """When same digit count, prefer higher confidence."""
        from detection import Detection
        from detection.filtering import choose_detection_to_remove
        det1 = Detection(bib_number="123", confidence=0.7, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        det2 = Detection(bib_number="456", confidence=0.9, bbox=[[0, 0], [10, 0], [10, 10], [0, 10]])
        # det2 has higher confidence, remove det1
        assert choose_detection_to_remove(det1, det2, 0, 1) == 0

    def test_detections_overlap_iou(self):
        """Test overlap detection via IoU."""
        from detection import Detection
        from detection.filtering import detections_overlap
        # Identical boxes have IoU = 1.0
        bbox = [[0, 0], [100, 0], [100, 100], [0, 100]]
        det1 = Detection(bib_number="1", confidence=0.9, bbox=bbox)
        det2 = Detection(bib_number="2", confidence=0.9, bbox=bbox)
        assert detections_overlap(det1, det2, iou_threshold=0.3, overlap_threshold=0.5)

    def test_detections_no_overlap(self):
        """Test non-overlapping boxes."""
        from detection import Detection
        from detection.filtering import detections_overlap
        det1 = Detection(bib_number="1", confidence=0.9, bbox=[[0, 0], [100, 0], [100, 100], [0, 100]])
        det2 = Detection(bib_number="2", confidence=0.9, bbox=[[200, 200], [300, 200], [300, 300], [200, 300]])
        assert not detections_overlap(det1, det2, iou_threshold=0.3, overlap_threshold=0.5)


class TestBibDetection:
    """Tests for bib number detection from images."""

    def test_detect_single_bib(self, ocr_reader):
        """Test detection of a single bib number (353)."""
        image_path = SAMPLES_DIR / "bib_353.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [d.bib_number for d in result.detections]

        assert "353" in bib_numbers, f"Expected bib 353, got: {bib_numbers}"

    def test_detect_another_single_bib(self, ocr_reader):
        """Test detection of a single bib number (353)."""
        image_path = SAMPLES_DIR / "bib_622.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [d.bib_number for d in result.detections]

        assert "622" in bib_numbers, f"Expected bib 622, got: {bib_numbers}"

    def test_detect_multiple_bibs(self, ocr_reader):
        """Test detection of multiple bib numbers (379, 328, 329)."""
        image_path = SAMPLES_DIR / "bib_379_328_329.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [d.bib_number for d in result.detections]

        # Check that at least some of the expected bibs are detected
        expected = {"379", "328", "329"}
        detected = set(bib_numbers)
        found = expected & detected

        assert len(found) >= 2, f"Expected at least 2 of {expected}, got: {bib_numbers}"

    def test_no_bib_detected(self, ocr_reader):
        """Test that typical race bib numbers are not detected in a non-race photo."""
        image_path = SAMPLES_DIR / "nobib.jpg"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)

        # Should not detect the specific bib numbers from our race photos
        # (OCR may find some numbers in any image, but not race-specific ones)
        race_bibs = {"353", "379", "328", "329"}
        detected = {d.bib_number for d in result.detections}

        assert not (race_bibs & detected), f"Found race bibs in non-race photo: {race_bibs & detected}"

    def test_detection_includes_confidence(self, ocr_reader):
        """Test that detections include confidence scores."""
        image_path = SAMPLES_DIR / "bib_353.JPG"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)

        assert len(result.detections) > 0, "Expected at least one detection"
        for det in result.detections:
            assert 0 <= det.confidence <= 1
            assert det.bbox is not None
            assert det.bib_number is not None

        # Check that grayscale image is returned
        assert result.ocr_grayscale is not None
        assert result.ocr_grayscale.ndim == 2  # Should be 2D grayscale

    def test_detect_four_bibs_hvv3729(self, ocr_reader):
        """Test detection of 4 bibs in HVV_3729 (photo 0ba02f00).

        This photo has 4 visible bib numbers: 539, 526, 527, 535.
        Each detection should have a unique bbox that can be used for snippet naming.
        """
        image_path = SAMPLES_DIR / "HVV_3729.jpg"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [d.bib_number for d in result.detections]

        # Should detect all 4 bibs
        expected = {"539", "526", "527", "535"}
        detected = set(bib_numbers)

        assert expected == detected, f"Expected {expected}, got {detected}"

        # Each bib should have a unique bbox (for snippet naming)
        bboxes = [str(d.bbox) for d in result.detections]
        assert len(bboxes) == len(set(bboxes)), "Bounding boxes should be unique"

    def test_detect_bibs_hvv3730(self, ocr_reader):
        """Test detection of bibs in HVV_3730 (photo 3069f311).

        This photo has 5-6 people with visible bib numbers.
        With unified filtering (aspect ratio, brightness, relative area),
        we reliably detect 539 (white region) and 526 (full image, large enough).
        540 is too small (relative_area < 0.001) to pass filtering consistently.
        """
        image_path = SAMPLES_DIR / "HVV_3730.jpg"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [d.bib_number for d in result.detections]

        # Should reliably detect these bibs (pass all filters)
        expected = {"539", "526"}
        detected = set(bib_numbers)

        assert expected == detected, f"Expected {expected}, got {detected}"


class TestSnippetGeneration:
    """Tests for bib snippet generation and naming."""

    def test_snippet_path_uses_bbox_hash(self):
        """Test that snippet paths use bbox hash for unique naming."""
        from utils import get_snippet_path, compute_bbox_hash
        from pathlib import Path

        cache_path = Path("/cache/abc123.jpg")
        bbox1 = [[100, 100], [200, 100], [200, 150], [100, 150]]
        bbox2 = [[300, 100], [400, 100], [400, 150], [300, 150]]

        path1 = get_snippet_path(cache_path, "123", bbox1)
        path2 = get_snippet_path(cache_path, "123", bbox2)

        # Same bib number but different bbox should give different paths
        assert path1 != path2

        # Path should contain the bib number
        assert "_bib123_" in path1.name
        assert "_bib123_" in path2.name

        # Path should contain bbox hash
        hash1 = compute_bbox_hash(bbox1)
        hash2 = compute_bbox_hash(bbox2)
        assert hash1 in path1.name
        assert hash2 in path2.name

    def test_bbox_hash_is_deterministic(self):
        """Test that bbox hash is deterministic for the same input."""
        from utils import compute_bbox_hash

        bbox = [[100, 200], [300, 200], [300, 400], [100, 400]]

        hash1 = compute_bbox_hash(bbox)
        hash2 = compute_bbox_hash(bbox)

        assert hash1 == hash2
        assert len(hash1) == 8  # 8-character hash

    def test_snippet_count_matches_detection_count(self, ocr_reader):
        """Test that snippet generation creates one snippet per detection."""
        import tempfile
        import shutil
        from pathlib import Path
        from utils import compute_bbox_hash, save_bib_snippet

        image_path = SAMPLES_DIR / "HVV_3729.jpg"
        with open(image_path, "rb") as f:
            image_data = f.read()

        result = detect_bib_numbers(ocr_reader, image_data)

        # Use DetectionResult to get detections at OCR scale
        scaled_detections = result.detections_at_ocr_scale()

        # Create temp directory for snippets
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Save snippets using the same logic as scan_album.py
            # Note: bboxes from detect_bib_numbers are in original coords,
            # so we use detections_at_ocr_scale() to get them at grayscale resolution
            for det, scaled_det in zip(result.detections, scaled_detections):
                bbox_hash = compute_bbox_hash(det.bbox)
                snippet_filename = f"test_photo_bib{det.bib_number}_{bbox_hash}.jpg"
                snippet_path = temp_dir / snippet_filename
                save_bib_snippet(result.ocr_grayscale, scaled_det.bbox, snippet_path)

            # Count saved snippets
            snippets = list(temp_dir.glob("*.jpg"))
            assert len(snippets) == len(result.detections), f"Expected {len(result.detections)} snippets, got {len(snippets)}"
        finally:
            shutil.rmtree(temp_dir)


class TestDatabase:
    """Tests for database operations."""

    def test_insert_and_retrieve_photo(self, temp_db):
        """Test inserting a photo and retrieving it."""
        photo_id = db.insert_photo(
            temp_db,
            album_url="https://photos.google.com/share/test",
            photo_url="https://lh3.googleusercontent.com/test123",
            thumbnail_url="https://lh3.googleusercontent.com/test123=w400",
        )

        assert photo_id is not None
        assert photo_id > 0

    def test_duplicate_photo_returns_existing_id(self, temp_db):
        """Test that inserting a duplicate photo returns the existing ID."""
        photo_url = "https://lh3.googleusercontent.com/unique123"

        id1 = db.insert_photo(temp_db, "https://album1", photo_url)
        id2 = db.insert_photo(temp_db, "https://album2", photo_url)

        assert id1 == id2

    def test_photo_exists(self, temp_db):
        """Test checking if a photo exists."""
        photo_url = "https://lh3.googleusercontent.com/exists123"

        assert not db.photo_exists(temp_db, photo_url)

        db.insert_photo(temp_db, "https://album", photo_url)

        assert db.photo_exists(temp_db, photo_url)

    def test_insert_bib_detection(self, temp_db):
        """Test inserting a bib detection."""
        photo_id = db.insert_photo(
            temp_db,
            album_url="https://album",
            photo_url="https://photo/bib",
        )

        detection_id = db.insert_bib_detection(
            temp_db,
            photo_id=photo_id,
            bib_number="353",
            confidence=0.95,
            bbox=[[10, 20], [100, 20], [100, 60], [10, 60]],
        )

        assert detection_id is not None
        assert detection_id > 0

    def test_get_photos_by_bib(self, temp_db):
        """Test retrieving photos by bib number."""
        # Insert photos with different bibs
        photo1_id = db.insert_photo(temp_db, "https://album", "https://photo1")
        photo2_id = db.insert_photo(temp_db, "https://album", "https://photo2")
        photo3_id = db.insert_photo(temp_db, "https://album", "https://photo3")

        db.insert_bib_detection(temp_db, photo1_id, "100", 0.9, [])
        db.insert_bib_detection(temp_db, photo1_id, "101", 0.8, [])
        db.insert_bib_detection(temp_db, photo2_id, "100", 0.85, [])
        db.insert_bib_detection(temp_db, photo3_id, "200", 0.9, [])

        # Query for bib 100
        photos = db.get_photos_by_bib(temp_db, ["100"])
        assert len(photos) == 2

        # Query for multiple bibs
        photos = db.get_photos_by_bib(temp_db, ["100", "200"])
        assert len(photos) == 3

        # Query for non-existent bib
        photos = db.get_photos_by_bib(temp_db, ["999"])
        assert len(photos) == 0

    def test_get_photos_by_bib_returns_matched_bibs(self, temp_db):
        """Test that matched_bibs field contains the matching bib numbers."""
        photo_id = db.insert_photo(temp_db, "https://album", "https://photo/multi")
        db.insert_bib_detection(temp_db, photo_id, "42", 0.9, [])
        db.insert_bib_detection(temp_db, photo_id, "43", 0.9, [])

        photos = db.get_photos_by_bib(temp_db, ["42"])
        assert len(photos) == 1
        assert "42" in photos[0]["matched_bibs"]

    def test_insert_photo_with_cache_path(self, temp_db):
        """Test inserting a photo with a cache path."""
        photo_id = db.insert_photo(
            temp_db,
            album_url="https://album",
            photo_url="https://photo/cached",
            cache_path="/path/to/cache/abc123.jpg",
        )

        cursor = temp_db.cursor()
        cursor.execute("SELECT cache_path FROM photos WHERE id = ?", (photo_id,))
        result = cursor.fetchone()

        assert result["cache_path"] == "/path/to/cache/abc123.jpg"

    def test_update_photo_cache_path(self, temp_db):
        """Test updating the cache path for an existing photo."""
        photo_id = db.insert_photo(
            temp_db,
            album_url="https://album",
            photo_url="https://photo/update_cache",
        )

        db.update_photo_cache_path(temp_db, photo_id, "/new/cache/path.jpg")

        cursor = temp_db.cursor()
        cursor.execute("SELECT cache_path FROM photos WHERE id = ?", (photo_id,))
        result = cursor.fetchone()

        assert result["cache_path"] == "/new/cache/path.jpg"

    def test_delete_bib_detections(self, temp_db):
        """Test deleting all bib detections for a photo."""
        photo_id = db.insert_photo(temp_db, "https://album", "https://photo/delete_test")
        db.insert_bib_detection(temp_db, photo_id, "100", 0.9, [])
        db.insert_bib_detection(temp_db, photo_id, "101", 0.8, [])

        # Verify detections exist
        cursor = temp_db.cursor()
        cursor.execute("SELECT COUNT(*) FROM bib_detections WHERE photo_id = ?", (photo_id,))
        assert cursor.fetchone()[0] == 2

        # Delete detections
        deleted = db.delete_bib_detections(temp_db, photo_id)
        assert deleted == 2

        # Verify detections are gone
        cursor.execute("SELECT COUNT(*) FROM bib_detections WHERE photo_id = ?", (photo_id,))
        assert cursor.fetchone()[0] == 0

    def test_get_photo_by_index(self, temp_db):
        """Test getting a photo by its 1-based index."""
        # Insert 3 photos
        db.insert_photo(temp_db, "https://album", "https://photo/first")
        db.insert_photo(temp_db, "https://album", "https://photo/second")
        db.insert_photo(temp_db, "https://album", "https://photo/third")

        # Get photo at index 2 (1-based)
        photo = db.get_photo_by_index(temp_db, 2)
        assert photo is not None
        assert photo["photo_url"] == "https://photo/second"

        # Get first photo
        photo = db.get_photo_by_index(temp_db, 1)
        assert photo is not None
        assert photo["photo_url"] == "https://photo/first"

        # Get last photo
        photo = db.get_photo_by_index(temp_db, 3)
        assert photo is not None
        assert photo["photo_url"] == "https://photo/third"

        # Out of range
        photo = db.get_photo_by_index(temp_db, 4)
        assert photo is None

        # Invalid index (0 or negative)
        photo = db.get_photo_by_index(temp_db, 0)
        assert photo is None
        photo = db.get_photo_by_index(temp_db, -1)
        assert photo is None

    def test_get_photo_count(self, temp_db):
        """Test counting photos in the database."""
        # Initially empty
        assert db.get_photo_count(temp_db) == 0

        # Add photos
        db.insert_photo(temp_db, "https://album", "https://photo/1")
        assert db.get_photo_count(temp_db) == 1

        db.insert_photo(temp_db, "https://album", "https://photo/2")
        assert db.get_photo_count(temp_db) == 2

        db.insert_photo(temp_db, "https://album", "https://photo/3")
        assert db.get_photo_count(temp_db) == 3
