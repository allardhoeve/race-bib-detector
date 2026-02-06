"""Tests for scan_album helpers."""

import pytest

from scan_album import resolve_face_mode


def test_resolve_face_mode_defaults() -> None:
    run_bib, run_face = resolve_face_mode(False, False)
    assert run_bib is True
    assert run_face is True


def test_resolve_face_mode_faces_only() -> None:
    run_bib, run_face = resolve_face_mode(True, False)
    assert run_bib is False
    assert run_face is True


def test_resolve_face_mode_no_faces() -> None:
    run_bib, run_face = resolve_face_mode(False, True)
    assert run_bib is True
    assert run_face is False


def test_resolve_face_mode_invalid() -> None:
    with pytest.raises(ValueError, match="faces_only and no_faces"):
        resolve_face_mode(True, True)
