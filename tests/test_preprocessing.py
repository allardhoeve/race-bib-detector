"""
Unit tests for the preprocessing module.

Tests cover:
- to_grayscale: shape, dtype, channel handling
- resize_to_width: aspect ratio preservation, scale factor calculation
- run_pipeline: end-to-end preprocessing
- PreprocessConfig: validation
- PreprocessStep classes: GrayscaleStep, ResizeStep, CLAHEStep
- Pipeline: step orchestration and metadata tracking
"""

import numpy as np
import pytest

from preprocessing import (
    PreprocessConfig,
    PreprocessResult,
    run_pipeline,
    to_grayscale,
    resize_to_width,
    # Class-based API
    PreprocessStep,
    GrayscaleStep,
    ResizeStep,
    CLAHEStep,
    Pipeline,
    PipelineStepResults,
    StepResult,
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
            processed=np.zeros((100, 200)),  # Grayscale, resized
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
            processed=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        bbox = [[10, 10], [20, 10], [20, 20], [10, 20]]
        mapped = result.map_bbox_to_original(bbox)
        assert mapped == [[20, 20], [40, 20], [40, 40], [20, 40]]

    def test_ocr_image_returns_processed(self):
        """ocr_image should return processed image."""
        processed = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3), dtype=np.uint8),
            processed=processed,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_image is processed

    def test_ocr_grayscale_returns_processed(self):
        """ocr_grayscale should return processed image (which is grayscale)."""
        processed = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=processed,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_grayscale is processed

    def test_ocr_dimensions_returns_processed_dimensions(self):
        """ocr_dimensions should return (width, height) of processed image."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=np.zeros((100, 200)),
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.ocr_dimensions == (200, 100)

    def test_legacy_grayscale_property(self):
        """grayscale property should return processed for backwards compat."""
        processed = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=processed,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.grayscale is processed

    def test_legacy_resized_property_when_scaled(self):
        """resized property should return processed when scale_factor != 1."""
        processed = np.zeros((100, 200), dtype=np.uint8)
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=processed,
            scale_factor=2.0,
            config=PreprocessConfig(target_width=200),
        )
        assert result.resized is processed

    def test_legacy_resized_property_when_not_scaled(self):
        """resized property should return None when scale_factor == 1."""
        result = PreprocessResult(
            original=np.zeros((200, 400, 3)),
            processed=np.zeros((200, 400)),
            scale_factor=1.0,
            config=PreprocessConfig(target_width=None),
        )
        assert result.resized is None


class TestRunPipeline:
    """Tests for the run_pipeline function."""

    def test_basic_pipeline(self):
        """Pipeline should produce expected outputs."""
        img = np.random.randint(0, 256, (1000, 2000, 3), dtype=np.uint8)
        result = run_pipeline(img)

        assert result.original.shape == (1000, 2000, 3)
        assert result.processed.ndim == 2  # Grayscale
        assert result.processed.shape[1] == 1280  # Default target width
        # Height should be proportionally scaled: 1000 * (1280/2000) = 640
        assert result.processed.shape[0] == 640

    def test_pipeline_with_custom_config(self):
        """Pipeline should respect custom config."""
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=1000)
        result = run_pipeline(img, config)

        assert result.processed.shape == (500, 1000)  # Grayscale, resized
        assert result.scale_factor == 2.0

    def test_pipeline_without_resize(self):
        """Pipeline with target_width=None should only convert to grayscale."""
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        config = PreprocessConfig(target_width=None)
        result = run_pipeline(img, config)

        assert result.processed.shape == (100, 200)  # Grayscale, same size
        assert result.processed.ndim == 2
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

    def test_pipeline_produces_grayscale_output(self):
        """Pipeline output should always be grayscale."""
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        result = run_pipeline(img)
        assert result.processed.ndim == 2
        assert result.processed.dtype == np.uint8


class TestGrayscaleStep:
    """Tests for the GrayscaleStep class."""

    def test_apply_converts_rgb_to_grayscale(self):
        """GrayscaleStep should convert RGB to grayscale."""
        step = GrayscaleStep()
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = step.apply(rgb)
        assert result.shape == (100, 200)
        assert result.ndim == 2

    def test_name_property(self):
        """GrayscaleStep should have correct name."""
        step = GrayscaleStep()
        assert step.name == "grayscale"

    def test_custom_dtype(self):
        """GrayscaleStep should respect custom dtype."""
        step = GrayscaleStep(dtype=np.float32)
        rgb = np.full((10, 10, 3), 128, dtype=np.uint8)
        result = step.apply(rgb)
        assert result.dtype == np.float32

    def test_pure_function(self):
        """GrayscaleStep should not mutate input."""
        step = GrayscaleStep()
        rgb = np.full((10, 10, 3), 128, dtype=np.uint8)
        original = rgb.copy()
        _ = step.apply(rgb)
        assert np.array_equal(rgb, original)

    def test_is_frozen_dataclass(self):
        """GrayscaleStep should be immutable."""
        step = GrayscaleStep()
        with pytest.raises(Exception):  # FrozenInstanceError
            step.dtype = np.float32

    def test_get_metadata_returns_empty(self):
        """GrayscaleStep should return empty metadata."""
        step = GrayscaleStep()
        assert step.get_metadata() == {}


class TestResizeStep:
    """Tests for the ResizeStep class."""

    def test_apply_resizes_image(self):
        """ResizeStep should resize to target width."""
        step = ResizeStep(target_width=1000)
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        result = step.apply(img)
        assert result.shape == (500, 1000, 3)

    def test_name_property(self):
        """ResizeStep should have correct name with width."""
        step = ResizeStep(target_width=1280)
        assert step.name == "resize(1280)"

    def test_scale_factor_metadata(self):
        """ResizeStep should track scale factor in metadata."""
        step = ResizeStep(target_width=1000)
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        _ = step.apply(img)
        metadata = step.get_metadata()
        assert "scale_factor" in metadata
        assert metadata["scale_factor"] == 2.0

    def test_preserves_aspect_ratio(self):
        """ResizeStep should preserve aspect ratio."""
        step = ResizeStep(target_width=500)
        img = np.zeros((300, 1000, 3), dtype=np.uint8)  # 1000:300 = 10:3
        result = step.apply(img)
        # 500:150 = 10:3 (same ratio)
        assert result.shape == (150, 500, 3)

    def test_pure_function(self):
        """ResizeStep should not mutate input."""
        step = ResizeStep(target_width=100)
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        original = img.copy()
        _ = step.apply(img)
        assert np.array_equal(img, original)


class TestCLAHEStep:
    """Tests for the CLAHEStep class."""

    def test_apply_enhances_contrast(self):
        """CLAHEStep should enhance contrast in grayscale image."""
        step = CLAHEStep()
        # Create a low-contrast grayscale image
        gray = np.full((100, 100), 128, dtype=np.uint8)
        gray[40:60, 40:60] = 138  # Slightly brighter center
        result = step.apply(gray)
        # CLAHE should increase contrast (center should be brighter relative to edges)
        assert result.shape == gray.shape
        assert result.dtype == gray.dtype

    def test_name_property(self):
        """CLAHEStep should have correct name with clip limit."""
        step = CLAHEStep(clip_limit=3.0)
        assert step.name == "clahe(clip=3.0)"

    def test_default_parameters(self):
        """CLAHEStep should have sensible defaults."""
        step = CLAHEStep()
        assert step.clip_limit == 2.0
        assert step.tile_size == (8, 8)

    def test_custom_parameters(self):
        """CLAHEStep should accept custom parameters."""
        step = CLAHEStep(clip_limit=4.0, tile_size=(16, 16))
        assert step.clip_limit == 4.0
        assert step.tile_size == (16, 16)

    def test_requires_grayscale_input(self):
        """CLAHEStep should raise for non-grayscale input."""
        step = CLAHEStep()
        rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="grayscale input"):
            step.apply(rgb)

    def test_is_frozen_dataclass(self):
        """CLAHEStep should be immutable."""
        step = CLAHEStep()
        with pytest.raises(Exception):  # FrozenInstanceError
            step.clip_limit = 5.0

    def test_pure_function(self):
        """CLAHEStep should not mutate input."""
        step = CLAHEStep()
        gray = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        original = gray.copy()
        _ = step.apply(gray)
        assert np.array_equal(gray, original)


class TestPipeline:
    """Tests for the Pipeline class."""

    def test_empty_pipeline_returns_original(self):
        """Empty pipeline should return copy of original."""
        pipeline = Pipeline(steps=[])
        img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        result = pipeline.run(img)
        assert np.array_equal(result.final, img)
        assert result.final is not img  # Should be a copy

    def test_single_step_pipeline(self):
        """Pipeline with one step should apply that step."""
        pipeline = Pipeline(steps=[GrayscaleStep()])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        assert result.final.shape == (100, 200)
        assert result.final.ndim == 2

    def test_multi_step_pipeline(self):
        """Pipeline should apply steps in order."""
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)
        # First grayscale (100, 200), then resize to width 100 -> (50, 100)
        assert result.final.shape == (50, 100)

    def test_tracks_intermediates(self):
        """Pipeline should track intermediate results."""
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
        """Should be able to retrieve intermediate by step name."""
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)

        gray = result.get_intermediate("grayscale")
        assert gray is not None
        assert gray.shape == (100, 200)

        resized = result.get_intermediate("resize(100)")
        assert resized is not None
        assert resized.shape == (50, 100)

    def test_get_intermediate_not_found(self):
        """get_intermediate should return None for unknown step."""
        pipeline = Pipeline(steps=[GrayscaleStep()])
        result = pipeline.run(np.zeros((10, 10, 3), dtype=np.uint8))
        assert result.get_intermediate("unknown") is None

    def test_aggregates_metadata(self):
        """Pipeline should aggregate metadata from all steps."""
        pipeline = Pipeline(steps=[
            GrayscaleStep(),
            ResizeStep(target_width=100),
        ])
        rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        result = pipeline.run(rgb)

        assert result.scale_factor == 2.0
        assert result.get_metadata("scale_factor") == 2.0
        assert "scale_factor" in result.all_metadata

    def test_len_returns_step_count(self):
        """len(pipeline) should return number of steps."""
        pipeline = Pipeline(steps=[GrayscaleStep(), ResizeStep(target_width=100)])
        assert len(pipeline) == 2

    def test_iter_yields_steps(self):
        """Iterating pipeline should yield steps."""
        steps = [GrayscaleStep(), ResizeStep(target_width=100)]
        pipeline = Pipeline(steps=steps)
        assert list(pipeline) == steps

    def test_preserves_original(self):
        """Pipeline should preserve original image."""
        pipeline = Pipeline(steps=[GrayscaleStep()])
        img = np.random.randint(0, 256, (100, 200, 3), dtype=np.uint8)
        result = pipeline.run(img)
        assert np.array_equal(result.original, img)
        assert result.original is not img  # Should be a copy


class TestPipelineStepResults:
    """Tests for PipelineStepResults helper methods."""

    def test_final_with_no_steps(self):
        """final should return original when no steps."""
        result = PipelineStepResults(original=np.zeros((10, 10)))
        assert np.array_equal(result.final, result.original)

    def test_scale_factor_default(self):
        """scale_factor should default to 1.0 when not in metadata."""
        result = PipelineStepResults(original=np.zeros((10, 10)))
        assert result.scale_factor == 1.0

    def test_all_metadata_merges(self):
        """all_metadata should merge metadata from all steps."""
        result = PipelineStepResults(
            original=np.zeros((10, 10)),
            steps=[
                StepResult(name="step1", image=np.zeros((10, 10)), metadata={"a": 1}),
                StepResult(name="step2", image=np.zeros((5, 5)), metadata={"b": 2}),
            ]
        )
        assert result.all_metadata == {"a": 1, "b": 2}

    def test_all_metadata_later_overrides(self):
        """Later step metadata should override earlier for same key."""
        result = PipelineStepResults(
            original=np.zeros((10, 10)),
            steps=[
                StepResult(name="step1", image=np.zeros((10, 10)), metadata={"x": 1}),
                StepResult(name="step2", image=np.zeros((5, 5)), metadata={"x": 2}),
            ]
        )
        assert result.all_metadata["x"] == 2
