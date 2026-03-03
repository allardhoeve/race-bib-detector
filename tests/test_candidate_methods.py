"""Tests for candidate finding methods (task-100)."""

from __future__ import annotations

import numpy as np
import pytest

from config import CandidateFindMethod
from detection.regions import find_bib_candidates


def _make_image_with_white_rect(
    width: int = 400,
    height: int = 400,
    rect_x: int = 100,
    rect_y: int = 100,
    rect_w: int = 120,
    rect_h: int = 80,
    bg_value: int = 30,
    rect_value: int = 240,
    channels: int = 0,
) -> np.ndarray:
    """Create a synthetic image with a white rectangle on a dark background.

    Args:
        channels: 0 for grayscale, 3 for RGB.
    """
    if channels == 3:
        img = np.full((height, width, 3), bg_value, dtype=np.uint8)
        img[rect_y:rect_y + rect_h, rect_x:rect_x + rect_w] = rect_value
    else:
        img = np.full((height, width), bg_value, dtype=np.uint8)
        img[rect_y:rect_y + rect_h, rect_x:rect_x + rect_w] = rect_value
    return img


class TestGrayscaleThreshold:
    def test_finds_white_region(self):
        img = _make_image_with_white_rect()
        candidates = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.GRAYSCALE_THRESHOLD,
        )
        passed = [c for c in candidates if c.passed]
        assert len(passed) >= 1

    def test_default_method_is_grayscale(self):
        """method=None defaults to GRAYSCALE_THRESHOLD."""
        img = _make_image_with_white_rect()
        default = find_bib_candidates(img, min_area=100)
        explicit = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.GRAYSCALE_THRESHOLD,
        )
        assert len(default) == len(explicit)


class TestHSVWhite:
    def test_finds_white_region_rgb(self):
        img = _make_image_with_white_rect(channels=3)
        candidates = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.HSV_WHITE,
        )
        passed = [c for c in candidates if c.passed]
        assert len(passed) >= 1

    def test_rejects_bright_skin_tone(self):
        """Bright warm-colored region (high V, high S) should not be found."""
        img = np.full((400, 400, 3), 30, dtype=np.uint8)
        # Warm skin tone: high R, moderate G, low B → high V, high S in HSV
        img[100:180, 100:220, 0] = 220  # R
        img[100:180, 100:220, 1] = 160  # G
        img[100:180, 100:220, 2] = 100  # B
        candidates = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.HSV_WHITE,
        )
        passed = [c for c in candidates if c.passed]
        assert len(passed) == 0

    def test_grayscale_input_falls_back(self):
        """HSV with grayscale input falls back to GRAYSCALE_THRESHOLD with warning."""
        img = _make_image_with_white_rect(channels=0)
        # Should not crash — falls back gracefully
        candidates = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.HSV_WHITE,
        )
        # Falls back to grayscale threshold, should still find the white rect
        passed = [c for c in candidates if c.passed]
        assert len(passed) >= 1


class TestNone:
    def test_returns_empty(self):
        img = _make_image_with_white_rect()
        candidates = find_bib_candidates(
            img, min_area=100, method=CandidateFindMethod.NONE,
        )
        assert candidates == []
