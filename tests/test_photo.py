"""Tests for the Photo and ImagePaths dataclasses."""

from pathlib import Path

from photo import Photo, ImagePaths, compute_photo_hash


class TestComputePhotoHash:
    """Tests for compute_photo_hash function."""

    def test_returns_8_chars(self):
        """Hash should always be 8 characters."""
        result = compute_photo_hash("http://example.com/photo.jpg")
        assert len(result) == 8

    def test_hex_characters_only(self):
        """Hash should contain only hex characters."""
        result = compute_photo_hash("http://example.com/photo.jpg")
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        """Same URL should always produce same hash."""
        url = "http://example.com/photo.jpg"
        assert compute_photo_hash(url) == compute_photo_hash(url)

    def test_different_urls_different_hashes(self):
        """Different URLs should produce different hashes."""
        hash1 = compute_photo_hash("http://example.com/photo1.jpg")
        hash2 = compute_photo_hash("http://example.com/photo2.jpg")
        assert hash1 != hash2


class TestPhoto:
    """Tests for Photo dataclass."""

    def test_auto_computes_hash(self):
        """Photo should auto-compute hash if not provided."""
        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
        )
        assert photo.photo_hash is not None
        assert len(photo.photo_hash) == 8

    def test_uses_provided_hash(self):
        """Photo should use provided hash if given."""
        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
            photo_hash="custom12",
        )
        assert photo.photo_hash == "custom12"

    def test_is_local_true_for_local_file(self):
        """Local file source should be local."""
        photo = Photo(
            photo_url="/path/to/photo.jpg",
            album_id="album1234",
            source_type="local_file",
        )
        assert photo.is_local is True


class TestPhotoFromLocalPath:
    """Tests for Photo.from_local_path factory method."""

    def test_creates_local_file_source(self):
        """from_local_path should create photo with local_file source type."""
        photo = Photo.from_local_path(
            file_path="/photos/vacation/img001.jpg",
            album_id="album1234",
        )
        assert photo.source_type == "local_file"
        assert photo.is_local is True

    def test_converts_path_to_string(self):
        """from_local_path should accept Path objects."""
        photo = Photo.from_local_path(
            file_path=Path("/photos/vacation/img001.jpg"),
            album_id="album1234",
        )
        assert photo.photo_url == "/photos/vacation/img001.jpg"
        assert photo.album_id == "album1234"

    def test_thumbnail_is_none(self):
        """from_local_path should set thumbnail_url to None."""
        photo = Photo.from_local_path(
            file_path="/photos/img.jpg",
            album_id="album1234",
        )
        assert photo.thumbnail_url is None


class TestPhotoFromDbRow:
    """Tests for Photo.from_db_row factory method."""

    def test_creates_photo_from_row(self):
        """from_db_row should populate all fields from dict."""
        row = {
            "id": 42,
            "photo_url": "http://example.com/photo.jpg",
            "album_id": "album1234",
            "thumbnail_url": "http://example.com/thumb.jpg",
            "photo_hash": "abc12345",
            "cache_path": "/cache/abc12345.jpg",
        }
        photo = Photo.from_db_row(row)

        assert photo.id == 42
        assert photo.photo_url == "http://example.com/photo.jpg"
        assert photo.album_id == "album1234"
        assert photo.thumbnail_url == "http://example.com/thumb.jpg"
        assert photo.photo_hash == "abc12345"
        assert photo.cache_path == Path("/cache/abc12345.jpg")
        assert photo.source_type == "local_file"

    def test_detects_local_file_from_url(self):
        """from_db_row should default to local_file."""
        row = {
            "photo_url": "/photos/img.jpg",
            "album_id": "album1234",
        }
        photo = Photo.from_db_row(row)
        assert photo.source_type == "local_file"
        assert photo.is_local is True

    def test_handles_missing_optional_fields(self):
        """from_db_row should handle missing optional fields."""
        row = {
            "photo_url": "http://example.com/photo.jpg",
            "album_id": "album1234",
        }
        photo = Photo.from_db_row(row)

        assert photo.id is None
        assert photo.thumbnail_url is None
        assert photo.cache_path is None


class TestPhotoToDict:
    """Tests for Photo.to_dict method."""

    def test_includes_all_fields(self):
        """to_dict should include all fields."""
        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
            thumbnail_url="http://example.com/thumb.jpg",
            photo_hash="abc12345",
            cache_path=Path("/cache/img.jpg"),
            source_type="local_file",
            id=42,
        )
        result = photo.to_dict()

        assert result["photo_url"] == "http://example.com/photo.jpg"
        assert result["album_id"] == "album1234"
        assert result["thumbnail_url"] == "http://example.com/thumb.jpg"
        assert result["photo_hash"] == "abc12345"
        assert result["cache_path"] == "/cache/img.jpg"
        assert result["source_type"] == "local_file"
        assert result["id"] == 42
        assert result["is_local"] is True

    def test_cache_path_none_serializes_as_none(self):
        """to_dict should serialize None cache_path as None."""
        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
        )
        result = photo.to_dict()
        assert result["cache_path"] is None


class TestPhotoGetPaths:
    """Tests for Photo.get_paths method."""

    def test_get_paths_returns_image_paths(self):
        """get_paths should return ImagePaths for photo with cache_path."""
        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
            cache_path=Path("/cache/abc12345.jpg"),
        )
        paths = photo.get_paths()

        assert isinstance(paths, ImagePaths)
        assert paths.cache_path == Path("/cache/abc12345.jpg")

    def test_get_paths_raises_without_cache_path(self):
        """get_paths should raise ValueError if cache_path not set."""
        import pytest

        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
        )
        with pytest.raises(ValueError, match="cache_path is not set"):
            photo.get_paths()


class TestImagePaths:
    """Tests for ImagePaths dataclass."""

    def test_for_cache_path_default_dirs(self):
        """for_cache_path should compute paths using default directories."""
        from photo import (
            DEFAULT_FACE_BOXED_DIR,
            DEFAULT_FACE_CANDIDATES_DIR,
            DEFAULT_FACE_EVIDENCE_DIR,
            DEFAULT_FACE_SNIPPETS_DIR,
            DEFAULT_GRAY_BBOX_DIR,
            DEFAULT_SNIPPETS_DIR,
        )

        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(cache_path)

        assert paths.cache_path == cache_path
        assert paths.gray_bbox_path == DEFAULT_GRAY_BBOX_DIR / "abc12345.jpg"
        assert paths.snippets_dir == DEFAULT_SNIPPETS_DIR
        assert paths.face_snippets_dir == DEFAULT_FACE_SNIPPETS_DIR
        assert paths.face_boxed_dir == DEFAULT_FACE_BOXED_DIR
        assert paths.face_candidates_dir == DEFAULT_FACE_CANDIDATES_DIR
        assert paths.face_evidence_dir == DEFAULT_FACE_EVIDENCE_DIR

    def test_for_cache_path_custom_dirs(self):
        """for_cache_path should use custom directories when provided."""
        cache_path = Path("/cache/abc12345.jpg")
        custom_gray = Path("/custom/gray")
        custom_snippets = Path("/custom/snippets")
        custom_face_snippets = Path("/custom/faces/snippets")
        custom_face_boxed = Path("/custom/faces/boxed")
        custom_face_candidates = Path("/custom/faces/candidates")
        custom_face_evidence = Path("/custom/faces/evidence")

        paths = ImagePaths.for_cache_path(
            cache_path,
            gray_bbox_dir=custom_gray,
            snippets_dir=custom_snippets,
            face_snippets_dir=custom_face_snippets,
            face_boxed_dir=custom_face_boxed,
            face_candidates_dir=custom_face_candidates,
            face_evidence_dir=custom_face_evidence,
        )

        assert paths.gray_bbox_path == custom_gray / "abc12345.jpg"
        assert paths.snippets_dir == custom_snippets
        assert paths.face_snippets_dir == custom_face_snippets
        assert paths.face_boxed_dir == custom_face_boxed
        assert paths.face_candidates_dir == custom_face_candidates
        assert paths.face_evidence_dir == custom_face_evidence

    def test_snippet_path(self):
        """snippet_path should return correct path for a bib."""
        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(
            cache_path,
            snippets_dir=Path("/snippets"),
        )

        snippet = paths.snippet_path("123", "deadbeef")

        assert snippet == Path("/snippets/abc12345_bib123_deadbeef.jpg")

    def test_snippet_path_different_bibs(self):
        """snippet_path should produce unique paths for different bibs."""
        cache_path = Path("/cache/photo.jpg")
        paths = ImagePaths.for_cache_path(cache_path, snippets_dir=Path("/snip"))

        path1 = paths.snippet_path("123", "aaa11111")
        path2 = paths.snippet_path("456", "bbb22222")

        assert path1 != path2
        assert "bib123" in str(path1)
        assert "bib456" in str(path2)

    def test_face_snippet_path(self):
        """face_snippet_path should return correct path for a face."""
        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(
            cache_path,
            face_snippets_dir=Path("/faces/snippets"),
        )

        snippet = paths.face_snippet_path(3)

        assert snippet == Path("/faces/snippets/abc12345_face3.jpg")

    def test_face_boxed_path(self):
        """face_boxed_path should return correct path for a boxed face preview."""
        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(
            cache_path,
            face_boxed_dir=Path("/faces/boxed"),
        )

        preview = paths.face_boxed_path(7)

        assert preview == Path("/faces/boxed/abc12345_face7_boxed.jpg")

    def test_face_evidence_path(self):
        """face_evidence_path should return correct path for evidence JSON."""
        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(
            cache_path,
            face_evidence_dir=Path("/faces/evidence"),
        )

        evidence = paths.face_evidence_path("deadbeef")

        assert evidence == Path("/faces/evidence/deadbeef_faces.json")

    def test_face_candidates_path(self):
        """face_candidates_path should return correct path for candidates preview."""
        cache_path = Path("/cache/abc12345.jpg")
        paths = ImagePaths.for_cache_path(
            cache_path,
            face_candidates_dir=Path("/faces/candidates"),
        )

        candidates = paths.face_candidates_path()

        assert candidates == Path("/faces/candidates/abc12345.jpg")
