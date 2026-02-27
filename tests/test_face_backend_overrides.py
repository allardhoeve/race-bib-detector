"""Tests for faces.backend.get_face_backend_with_overrides (task-028)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from faces.backend import get_face_backend_with_overrides


def test_dnn_backend_override_confidence():
    """Returned DNN backend uses the overridden confidence_min, not the config default."""
    with patch("pathlib.Path.exists", return_value=True), \
         patch("cv2.dnn.readNetFromCaffe", return_value=MagicMock()):
        backend = get_face_backend_with_overrides("opencv_dnn_ssd", confidence_min=0.99)
    assert backend.confidence_min == 0.99


def test_haar_backend_override_neighbors():
    """Returned Haar backend uses the overridden min_neighbors, not the config default."""
    mock_cascade = MagicMock()
    mock_cascade.empty.return_value = False
    with patch("cv2.CascadeClassifier", return_value=mock_cascade):
        backend = get_face_backend_with_overrides("opencv_haar", min_neighbors=42)
    assert backend.min_neighbors == 42


def test_unknown_kwarg_raises():
    """Passing an unknown kwarg raises ValueError regardless of backend."""
    with pytest.raises(ValueError, match="Unknown kwargs"):
        get_face_backend_with_overrides(foo=1)
