"""TDD tests for task-087: verify full-image OCR fallback is removed.

Updated by task-100: full_image is now a composable OCR method (not a
hardcoded fallback), so DetectionSource includes both values.
"""


def test_detection_source_type_includes_both():
    """DetectionSource allows both 'white_region' and 'full_image' (task-100)."""
    from detection.types import DetectionSource
    import typing
    args = typing.get_args(DetectionSource)
    assert "white_region" in args
    assert "full_image" in args


def test_full_image_confidence_threshold_removed():
    """config should not have FULL_IMAGE_CONFIDENCE_THRESHOLD."""
    import config
    assert not hasattr(config, "FULL_IMAGE_CONFIDENCE_THRESHOLD")


def test_extract_bib_detections_removed():
    """extract_bib_detections should not exist in detector module."""
    import detection.detector as det
    assert not hasattr(det, "extract_bib_detections")


def test_extract_bib_detections_not_in_init():
    """extract_bib_detections should not be exported from detection package."""
    import detection
    assert not hasattr(detection, "extract_bib_detections")
