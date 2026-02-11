"""Tests for the Photo dataclass — behavioral tests only."""

from photo import Photo


class TestPhotoGetPaths:
    """Tests for Photo.get_paths method."""

    def test_get_paths_raises_without_cache_path(self):
        """get_paths should raise ValueError if cache_path not set."""
        import pytest

        photo = Photo(
            photo_url="http://example.com/photo.jpg",
            album_id="album1234",
        )
        with pytest.raises(ValueError, match="cache_path is not set"):
            photo.get_paths()
