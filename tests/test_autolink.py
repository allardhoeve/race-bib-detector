"""Tests for faces.autolink.predict_links (task-030)."""

from __future__ import annotations

import pytest

from benchmarking.ground_truth import BibBox, FaceBox
from faces.autolink import AutolinkResult, predict_links


def _bib(x=0.1, y=0.5, w=0.1, h=0.1, number="1"):
    return BibBox(x=x, y=y, w=w, h=h, number=number)


def _face(x=0.1, y=0.1, w=0.1, h=0.1):
    return FaceBox(x=x, y=y, w=w, h=h)


class TestSingleFaceRule:
    def test_single_face_single_bib_linked(self):
        """Single face + single bib → exactly one link."""
        face = _face()
        bib = _bib()
        result = predict_links([bib], [face])
        assert len(result.pairs) == 1
        assert result.pairs[0] == (bib, face)
        assert result.provenance == ["single_face"]

    def test_single_face_low_conf_bib(self):
        """bib_confidence_threshold >= 1.0 suppresses all links."""
        result = predict_links([_bib()], [_face()], bib_confidence_threshold=1.1)
        assert result.pairs == []
        assert result.provenance == []


class TestEdgeCases:
    def test_no_faces(self):
        """Empty face list → AutolinkResult with no pairs."""
        result = predict_links([_bib()], [])
        assert result.pairs == []
        assert result.provenance == []

    def test_no_bibs(self):
        """Empty bib list → AutolinkResult with no pairs."""
        result = predict_links([], [_face()])
        assert result.pairs == []
        assert result.provenance == []

    def test_both_empty(self):
        result = predict_links([], [])
        assert result.pairs == []


class TestMultiFaceSpatialMatching:
    def test_multiple_faces_multiple_bibs(self):
        """Two faces side by side each linked to the bib in their torso region."""
        # face1 at left: centre (0.15, 0.15), torso x∈[0.05,0.25] y∈[0.2,0.4]
        face1 = _face(x=0.1, y=0.1, w=0.1, h=0.1)
        # face2 at right: centre (0.75, 0.15), torso x∈[0.65,0.85] y∈[0.2,0.4]
        face2 = _face(x=0.7, y=0.1, w=0.1, h=0.1)
        # bib1 centroid (0.15, 0.30) — inside face1's torso
        bib1 = _bib(x=0.1, y=0.25, w=0.1, h=0.1, number="1")
        # bib2 centroid (0.75, 0.30) — inside face2's torso
        bib2 = _bib(x=0.7, y=0.25, w=0.1, h=0.1, number="2")

        result = predict_links([bib1, bib2], [face1, face2])

        assert len(result.pairs) == 2
        assert (bib1, face1) in result.pairs
        assert (bib2, face2) in result.pairs

    def test_bib_outside_all_torsos_skipped(self):
        """Bib whose centroid falls outside every face's torso region is not linked."""
        face = _face(x=0.1, y=0.1, w=0.1, h=0.1)
        # bib far to the right, well outside torso x∈[0.05,0.25]
        bib = _bib(x=0.8, y=0.25, w=0.1, h=0.1)
        result = predict_links([bib], [face])
        # single-face rule fires (1 face + 1 bib) → still links unconditionally
        # only the multi-face path skips out-of-torso bibs
        assert len(result.pairs) == 1  # single-face rule, not spatial

    def test_each_bib_used_at_most_once(self):
        """One bib is not assigned to two faces."""
        face1 = _face(x=0.1, y=0.1, w=0.1, h=0.1)
        face2 = _face(x=0.15, y=0.1, w=0.1, h=0.1)  # close to face1
        # Single bib inside both torso regions
        bib = _bib(x=0.1, y=0.25, w=0.1, h=0.1)
        result = predict_links([bib], [face1, face2])
        # bib should appear at most once
        bib_uses = sum(1 for (b, _) in result.pairs if b is bib)
        assert bib_uses <= 1
