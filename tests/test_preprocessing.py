"""
Unit tests for the preprocessing module — behavioral tests only.

Covers: error handling, algorithm correctness, side-effect validation,
conditional behavior, and end-to-end pipeline behavior.
"""

import numpy as np
import pytest

from preprocessing import (
    PreprocessConfig,
    PreprocessResult,
    run_pipeline,
    to_grayscale,
    resize_to_width,
    GrayscaleStep,
    ResizeStep,
    CLAHEStep,
    Pipeline,
)


class TestToGrayscale:
    """Tests for the to_grayscale function."""

    def test_pure_function_no_mutation(self):
        """Input should not be modified."""
        rgb = np.full((10, 10, 3), 128, dtype=np.uint8)
        original_data = rgb.copy()
        _ = to_grayscale(rgb)
        assert np.array_equal(rgb, original_data)

    def test_white_image_produces_white_gray(self):
        white = np.full((10, 10, 3), 255, dtype=np.uint8)
        gray = to_grayscale(white)
        assert np.all(gray == 255)

    def test_black_image_produces_black_gray(self):
        black = np.zeros((10, 10, 3), dtype=np.uint8)
        gray = to_grayscale(black)
        assert np.all(gray == 0)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Expected numpy.ndarray"):
            to_grayscale([[1, 2], [3, 4]])

    def test_empty_array_raises(self):
        with pytest.raises(ValueError):
            to_grayscale(np.array([]))

    def test_1d_array_raises(self):
        with pytest.raises(ValueError, match="2D or 3D"):
            to_grayscale(np.array([1, 2, 3]))

    def test_4d_array_raises(self):
        with pytest.raises(ValueError, match="2D or 3D"):
            to_grayscale(np.zeros((1, 2, 3, 4)))

    def test_unsupported_channels_raises(self):
        with pytest.raises(ValueError, match="Unsupported number of channels"):
            to_grayscale(np.zeros((10, 10, 5), dtype=np.uint8))


class TestResizeToWidth:
    """Tests for the resize_to_width function."""

    def test_downscale_preserves_aspect_ratio(self):
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 1000)
        assert resized.shape == (500, 1000, 3)

    def test_scale_factor_calculation(self):
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 1000)
        assert scale == 2.0

    def test_upscale_preserves_aspect_ratio(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        resized, scale = resize_to_width(img, 400)
        assert resized.shape == (200, 400, 3)
        assert scale == 0.5

    def test_pure_function_no_mutation(self):
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original_data = img.copy()
        _ = resize_to_width(img, 100)
        assert np.array_equal(img, original_data)

    def test_invalid_width_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            resize_to_width(np.zeros((100, 200, 3)), 0)

    def test_invalid_width_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            resize_to_width(np.zeros((100, 200, 3)), -100)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Expected numpy.ndarray"):
            resize_to_width([[1, 2], [3, 4]], 100)

    def test_invalid_width_type_raises(self):
        with pytest.raises(TypeError, match="target_width must be int"):
            resize_to_width(np.zeros((100, 200, 3)), 100.5)

    def test_empty_array_raises(self):
        with pytest.raises(ValueError):
            resize_to_width(np.array([]), 100)


class TestPreprocessConfig:
    """Tests for PreprocessConfig validation."""

    def test_negative_width_raises(self):
        config = PreprocessConfig(target_width=-100)
        with pytest.raises(ValueError, match="positive"):
            config.validate()

    def test_zero_width_raises(self):
        config = PreprocessConfig(target_width=0)
        with pytest.raises(ValueError, match="positive"):
            config.validate()

    def test_too_small_width_raises(self):
        config = PreprocessConfig(target_width=50)
        with pytest.raises(ValueError, match="too small"):
            config.validate()

    def test_too_large_width_raises(self):
        config = PreprocessConfig(target_width=10000)
        with pytest.raises(ValueError, match="very large"):
            config.validate()


class TestPreprocessResult:
    """Tests for PreprocessResult coordinate mapping."""

    def test_map_to_original_coords(self):
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        x, y = result.map_to_original_coords(50, 25)
        assert x == 100.0
        assert y == 50.0

    def test_map_bbox_to_original(self):
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        bbox = [[10, 10], [20, 10], [20, 20], [10, 20]]
        mapped = result.map_bbox_to_original(bbox)
        assert mapped == [[20, 20], [40, 20], [40, 40], [20, 40]]

    def test_legacy_resized_property_when_scaled(self):
        """resized returns processed when scale_factor != 1, None otherwise."""
        processed = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=processed,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.resized is processed

        result_unscaled = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=np.zeros((200, 400)),
            scale_factor=1.0,
            config=PreprocessConfig(target_width=None),
        )
        assert result_unscaled.resized is None


class TestRunPipeline:
    """Tests for the run_pipeline function."""

    def test_basic_pipeline(self):
        img = np.random.randint(0, 256, (1000, 2000, 3), dtype=np.uint8)
        result = run_pipeline(img)
        assert result.original.shape == (1000, 2000, 3)
        assert result.processed.ndim == 2
        assert result.processed.shape[1] == 1280
        assert result.processed.shape[0] == 640

    def test_pipeline_with_custom_config(self):
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=1000)
        result = run_pipeline(img, config)
        assert result.processed.shape == (500, 1000)
        assert result.scale_factor == 2.0

    def test_pipeline_without_resize(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=None)
        result = run_pipeline(img, config)
        assert result.processed.shape == (100, 200)
        assert result.scale_factor == 1.0

    def test_pipeline_preserves_original(self):
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original_data = img.copy()
        result = run_pipeline(img)
        assert np.array_equal(result.original, original_data)
        assert result.original is not img

    def test_pipeline_invalid_config_raises(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=-100)
        with pytest.raises(ValueError):
            run_pipeline(img, config)

    def test_pipeline_invalid_input_raises(self):
        with pytest.raises(TypeError):
            run_pipeline("not an image")

    def test_pipeline_produces_grayscale_output(self):
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        result = run_pipeline(img)
        assert result.processed.ndim == 2
        assert result.processed.dtype == np.uint8


class TestGrayscaleStep:
    """Tests for the GrayscaleStep class."""

    def test_apply_converts_rgb_to_grayscale(self):
        step = GrayscaleStep()
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = step.apply(rgb)
        assert result.shape == (100, 200)
        assert result.ndim == 2

    def test_pure_function(self):
        step = GrayscaleStep()
        rgb = np.full((10, 10, 3), 128, dtype=np.uint8)
        original = rgb.copy()
        _ = step.apply(rgb)
        assert np.array_equal(rgb, original)


class TestResizeStep:
    """Tests for the ResizeStep class."""

    def test_apply_resizes_image(self):
        step = ResizeStep(target_width=1000)
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        result = step.apply(img)
        assert result.shape == (500, 1000, 3)

    def test_scale_factor_metadata(self):
        step = ResizeStep(target_width=1000)
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        _ = step.apply(img)
        metadata = step.get_metadata()
        assert metadata["scale_factor"] == 2.0

    def test_preserves_aspect_ratio(self):
        step = ResizeStep(target_width=500)
        img = np.zeros((300, 1000, 3), dtype=np.uint8)
        result = step.apply(img)
        assert result.shape == (150, 500, 3)

    def test_pure_function(self):
        step = ResizeStep(target_width=100)
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original = img.copy()
        _ = step.apply(img)
        assert np.array_equal(img, original)


class TestCLAHEStep:
    """Tests for the CLAHEStep class."""

    def test_apply_enhances_contrast(self):
        step = CLAHEStep()
        gray = np.full((100, 100), 128, dtype=np.uint8)
        gray[40:60, 40:60] = 138
        result = step.apply(gray)
        assert result.shape == gray.shape
        assert result.dtype == gray.dtype

    def test_requires_grayscale_input(self):
        step = CLAHEStep()
        rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="grayscale input"):
            step.apply(rgb)

    def test_pure_function(self):
        step = CLAHEStep()
        gray = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        original = gray.copy()
        _ = step.apply(gray)
        assert np.array_equal(gray, original)


class TestPipeline:
    """Tests for the Pipeline class."""

    def test_empty_pipeline_returns_original(self):
        pipeline = Pipeline(steps=[])
        img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        result = pipeline.run(img)
        assert np.array_equal(result.final, img)
        assert result.final is not img

    def test_multi_step_pipeline(self):
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        assert result.final.shape == (50, 100)

    def test_tracks_intermediates(self):
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        assert len(result.steps) == 2
        assert result.steps[0].name == "grayscale"
        assert result.steps[0].image.shape == (100, 200)
        assert result.steps[1].name == "resize(100)"
        assert result.steps[1].image.shape == (50, 100)

    def test_get_intermediate_by_name(self):
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        assert result.get_intermediate("grayscale").shape == (100, 200)
        assert result.get_intermediate("unknown") is None

    def test_aggregates_metadata(self):
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        assert result.scale_factor == 2.0

    def test_preserves_original(self):
        pipeline = Pipeline(steps=[GrayscaleStep()])
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        result = pipeline.run(img)
        assert np.array_equal(result.original, img)
        assert result.original is not img
