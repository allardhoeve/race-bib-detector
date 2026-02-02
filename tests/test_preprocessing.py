"""
Unit tests for the preprocessing module.

Tests cover:
- to_grayscale: shape, dtype, channel handling
- resize_to_width: aspect ratio preservation, scale factor calculation
- run_pipeline: end-to-end preprocessing
- PreprocessConfig: validation
"""

import numpy as np
import pytest

from preprocessing import (
    PreprocessConfig,
    PreprocessResult,
    run_pipeline,
    to_grayscale,
    resize_to_width,
)


class TestToGrayscale:
    """Tests for the to_grayscale function."""

    def test_rgb_to_grayscale_shape(self):
        """RGB image should become 2D grayscale."""
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        gray = to_grayscale(rgb)
        assert gray.shape == (100, 200)
        assert gray.ndim == 2

    def test_rgb_to_grayscale_dtype(self):
        """Output should have specified dtype."""
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        gray = to_grayscale(rgb, dtype=np.uint8)
        assert gray.dtype == np.uint8

    def test_rgba_to_grayscale(self):
        """RGBA image should work, dropping alpha channel."""
        rgba = np.zeros((100, 200, 4), dtype=np.uint8)
        rgba[:, :, 3] = 255  # Opaque alpha
        gray = to_grayscale(rgba)
        assert gray.shape == (100, 200)
        assert gray.dtype == np.uint8

    def test_already_grayscale(self):
        """Grayscale input should return a copy."""
        gray_input = np.random.randint(0, 256, (100, 200), dtype=np.uint8)
        gray_output = to_grayscale(gray_input)
        assert gray_output.shape == gray_input.shape
        assert np.array_equal(gray_output, gray_input)
        # Should be a copy, not same object
        assert gray_output is not gray_input

    def test_single_channel_3d(self):
        """Single channel 3D array should work."""
        single = np.zeros((100, 200, 1), dtype=np.uint8)
        gray = to_grayscale(single)
        assert gray.shape == (100, 200)

    def test_pure_function_no_mutation(self):
        """Input should not be modified."""
        rgb = np.full((10, 10, 3), 128, dtype=np.uint8)
        original_data = rgb.copy()
        _ = to_grayscale(rgb)
        assert np.array_equal(rgb, original_data)

    def test_white_image_produces_white_gray(self):
        """White RGB image should produce white grayscale."""
        white = np.full((10, 10, 3), 255, dtype=np.uint8)
        gray = to_grayscale(white)
        assert np.all(gray == 255)

    def test_black_image_produces_black_gray(self):
        """Black RGB image should produce black grayscale."""
        black = np.zeros((10, 10, 3), dtype=np.uint8)
        gray = to_grayscale(black)
        assert np.all(gray == 0)

    def test_invalid_type_raises(self):
        """Non-ndarray input should raise TypeError."""
        with pytest.raises(TypeError, match="Expected numpy.ndarray"):
            to_grayscale([[1, 2], [3, 4]])

    def test_empty_array_raises(self):
        """Empty array should raise ValueError."""
        with pytest.raises(ValueError):
            to_grayscale(np.array([]))

    def test_1d_array_raises(self):
        """1D array should raise ValueError."""
        with pytest.raises(ValueError, match="2D or 3D"):
            to_grayscale(np.array([1, 2, 3]))

    def test_4d_array_raises(self):
        """4D array should raise ValueError."""
        with pytest.raises(ValueError, match="2D or 3D"):
            to_grayscale(np.zeros((1, 2, 3, 4)))

    def test_unsupported_channels_raises(self):
        """Unsupported channel count should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported number of channels"):
            to_grayscale(np.zeros((10, 10, 5), dtype=np.uint8))


class TestResizeToWidth:
    """Tests for the resize_to_width function."""

    def test_downscale_preserves_aspect_ratio(self):
        """Downscaling should preserve aspect ratio."""
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 1000)
        assert resized.shape == (500, 1000, 3)

    def test_scale_factor_calculation(self):
        """Scale factor should be original_width / target_width."""
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 1000)
        assert scale == 2.0

    def test_upscale_preserves_aspect_ratio(self):
        """Upscaling should preserve aspect ratio."""
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 400)
        assert resized.shape == (200, 400, 3)
        assert scale == 0.5

    def test_same_width_returns_copy(self):
        """Same target width should return copy with scale 1.0."""
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 200)
        assert resized.shape == img.shape
        assert scale == 1.0
        assert np.array_equal(resized, img)
        assert resized is not img  # Should be a copy

    def test_grayscale_image(self):
        """Should work with 2D grayscale images."""
        gray = np.zeros((1000, 2000), dtype=np.uint8)
        resized, scale = resize_to_width(gray, 1000)
        assert resized.shape == (500, 1000)
        assert scale == 2.0

    def test_preserves_dtype(self):
        """Output should have same dtype as input."""
        for dtype in [np.uint8, np.float32, np.uint16]:
            img = np.zeros((100, 200, 3), dtype=dtype)
            resized, _ = resize_to_width(img, 100)
            assert resized.dtype == dtype

    def test_pure_function_no_mutation(self):
        """Input should not be modified."""
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original_data = img.copy()
        _ = resize_to_width(img, 100)
        assert np.array_equal(img, original_data)

    def test_invalid_width_zero_raises(self):
        """Zero width should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            resize_to_width(np.zeros((100, 200, 3)), 0)

    def test_invalid_width_negative_raises(self):
        """Negative width should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            resize_to_width(np.zeros((100, 200, 3)), -100)

    def test_invalid_type_raises(self):
        """Non-ndarray input should raise TypeError."""
        with pytest.raises(TypeError, match="Expected numpy.ndarray"):
            resize_to_width([[1, 2], [3, 4]], 100)

    def test_invalid_width_type_raises(self):
        """Non-int width should raise TypeError."""
        with pytest.raises(TypeError, match="target_width must be int"):
            resize_to_width(np.zeros((100, 200, 3)), 100.5)

    def test_empty_array_raises(self):
        """Empty array should raise ValueError."""
        with pytest.raises(ValueError):
            resize_to_width(np.array([]), 100)


class TestPreprocessConfig:
    """Tests for PreprocessConfig validation."""

    def test_default_config_valid(self):
        """Default config should be valid."""
        config = PreprocessConfig()
        config.validate()  # Should not raise

    def test_none_target_width_valid(self):
        """None target_width (skip resize) should be valid."""
        config = PreprocessConfig(target_width=None)
        config.validate()

    def test_negative_width_raises(self):
        """Negative target_width should raise ValueError."""
        config = PreprocessConfig(target_width=-100)
        with pytest.raises(ValueError, match="positive"):
            config.validate()

    def test_zero_width_raises(self):
        """Zero target_width should raise ValueError."""
        config = PreprocessConfig(target_width=0)
        with pytest.raises(ValueError, match="positive"):
            config.validate()

    def test_too_small_width_raises(self):
        """Very small target_width should raise ValueError."""
        config = PreprocessConfig(target_width=50)
        with pytest.raises(ValueError, match="too small"):
            config.validate()

    def test_too_large_width_raises(self):
        """Very large target_width should raise ValueError."""
        config = PreprocessConfig(target_width=10000)
        with pytest.raises(ValueError, match="very large"):
            config.validate()

    def test_config_is_immutable(self):
        """Config should be frozen (immutable)."""
        config = PreprocessConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.target_width = 500


class TestPreprocessResult:
    """Tests for PreprocessResult coordinate mapping."""

    def test_map_to_original_coords(self):
        """Coordinate mapping should use scale factor."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=np.zeros((200, 400)),
            resized=np.zeros((100, 200, 3)),
            resized_grayscale=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        x, y = result.map_to_original_coords(50, 25)
        assert x == 100.0
        assert y == 50.0

    def test_map_bbox_to_original(self):
        """Bounding box mapping should scale all points."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=np.zeros((200, 400)),
            resized=np.zeros((100, 200, 3)),
            resized_grayscale=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        bbox = [[10, 10], [20, 10], [20, 20], [10, 20]]
        mapped = result.map_bbox_to_original(bbox)
        assert mapped == [[20, 20], [40, 20], [40, 40], [20, 40]]

    def test_ocr_image_returns_resized_when_available(self):
        """ocr_image should return resized image when available."""
        original = np.zeros((200, 400, 3), dtype=np.uint8)
        resized = np.zeros((100, 200, 3), dtype=np.uint8)
        result = PreprocessResult(
            original=original,
            grayscale=np.zeros((200, 400)),
            resized=resized,
            resized_grayscale=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_image is resized

    def test_ocr_image_returns_original_when_no_resize(self):
        """ocr_image should return original when resized is None."""
        original = np.zeros((200, 400, 3), dtype=np.uint8)
        result = PreprocessResult(
            original=original,
            grayscale=np.zeros((200, 400)),
            resized=None,
            resized_grayscale=None,
            scale_factor=1.0,
            config=PreprocessConfig(target_width=None),
        )
        assert result.ocr_image is original

    def test_ocr_grayscale_returns_resized_when_available(self):
        """ocr_grayscale should return resized grayscale when available."""
        grayscale = np.zeros((200, 400), dtype=np.uint8)
        resized_grayscale = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=grayscale,
            resized=np.zeros((100, 200, 3)),
            resized_grayscale=resized_grayscale,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_grayscale is resized_grayscale

    def test_ocr_grayscale_returns_original_when_no_resize(self):
        """ocr_grayscale should return original grayscale when resized is None."""
        grayscale = np.zeros((200, 400), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=grayscale,
            resized=None,
            resized_grayscale=None,
            scale_factor=1.0,
            config=PreprocessConfig(target_width=None),
        )
        assert result.ocr_grayscale is grayscale

    def test_ocr_dimensions_returns_resized_dimensions(self):
        """ocr_dimensions should return (width, height) of resized image."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=np.zeros((200, 400)),
            resized=np.zeros((100, 200, 3)),
            resized_grayscale=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_dimensions == (200, 100)

    def test_ocr_dimensions_returns_original_dimensions_when_no_resize(self):
        """ocr_dimensions should return original dimensions when no resize."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            grayscale=np.zeros((200, 400)),
            resized=None,
            resized_grayscale=None,
            scale_factor=1.0,
            config=PreprocessConfig(target_width=None),
        )
        assert result.ocr_dimensions == (400, 200)


class TestRunPipeline:
    """Tests for the run_pipeline function."""

    def test_basic_pipeline(self):
        """Pipeline should produce expected outputs."""
        img = np.random.randint(0, 256, (1000, 2000, 3), dtype=np.uint8)
        result = run_pipeline(img)

        assert result.original.shape == (1000, 2000, 3)
        assert result.grayscale.shape == (1000, 2000)
        assert result.resized is not None
        assert result.resized.shape[1] == 1280  # Default target width
        assert result.resized_grayscale is not None

    def test_pipeline_with_custom_config(self):
        """Pipeline should respect custom config."""
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=1000)
        result = run_pipeline(img, config)

        assert result.resized.shape == (500, 1000, 3)
        assert result.scale_factor == 2.0

    def test_pipeline_without_resize(self):
        """Pipeline with target_width=None should skip resize."""
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=None)
        result = run_pipeline(img, config)

        assert result.resized is None
        assert result.resized_grayscale is None
        assert result.scale_factor == 1.0

    def test_pipeline_preserves_original(self):
        """Original image should be a copy, not reference."""
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original_data = img.copy()
        result = run_pipeline(img)

        assert np.array_equal(result.original, original_data)
        assert result.original is not img

    def test_pipeline_invalid_config_raises(self):
        """Pipeline with invalid config should raise."""
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=-100)
        with pytest.raises(ValueError):
            run_pipeline(img, config)

    def test_pipeline_invalid_input_raises(self):
        """Pipeline with invalid input should raise."""
        with pytest.raises(TypeError):
            run_pipeline("not an image")
