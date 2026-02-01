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


class TestBibDetection:
    """Tests for bib number detection from images."""

    def test_detect_single_bib(self, ocr_reader):
        """Test detection of a single bib number (353)."""
        image_path = SAMPLES_DIR / "bib_353.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        bibs, _ = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [b["bib_number"] for b in bibs]

        assert "353" in bib_numbers, f"Expected bib 353, got: {bib_numbers}"

    def test_detect_another_single_bib(self, ocr_reader):
        """Test detection of a single bib number (353)."""
        image_path = SAMPLES_DIR / "bib_622.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        bibs, _ = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [b["bib_number"] for b in bibs]

        assert "622" in bib_numbers, f"Expected bib 622, got: {bib_numbers}"

    def test_detect_multiple_bibs(self, ocr_reader):
        """Test detection of multiple bib numbers (379, 328, 329)."""
        image_path = SAMPLES_DIR / "bib_379_328_329.JPG"
        assert image_path.exists(), f"Sample image not found: {image_path}"

        with open(image_path, "rb") as f:
            image_data = f.read()

        bibs, _ = detect_bib_numbers(ocr_reader, image_data)
        bib_numbers = [b["bib_number"] for b in bibs]

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

        bibs, _ = detect_bib_numbers(ocr_reader, image_data)

        # Should not detect the specific bib numbers from our race photos
        # (OCR may find some numbers in any image, but not race-specific ones)
        race_bibs = {"353", "379", "328", "329"}
        detected = {b["bib_number"] for b in bibs}

        assert not (race_bibs & detected), f"Found race bibs in non-race photo: {race_bibs & detected}"

    def test_detection_includes_confidence(self, ocr_reader):
        """Test that detections include confidence scores."""
        image_path = SAMPLES_DIR / "bib_353.JPG"

        with open(image_path, "rb") as f:
            image_data = f.read()

        bibs, grayscale = detect_bib_numbers(ocr_reader, image_data)

        assert len(bibs) > 0, "Expected at least one detection"
        for bib in bibs:
            assert "confidence" in bib
            assert 0 <= bib["confidence"] <= 1
            assert "bbox" in bib
            assert "bib_number" in bib

        # Check that grayscale image is returned
        assert grayscale is not None
        assert grayscale.ndim == 2  # Should be 2D grayscale


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
