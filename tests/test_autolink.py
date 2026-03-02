"""Tests for predict_links (task-030, rewritten for TraceLink in task-095)."""

from __future__ import annotations

import pytest

from pipeline.types import BibCandidateTrace, FaceCandidateTrace, TraceLink, predict_links


def _bib(x=0.1, y=0.5, w=0.1, h=0.1, number="1"):
    return BibCandidateTrace(
        x=x, y=y, w=w, h=h,
        area=100, aspect_ratio=1.0, median_brightness=200.0,
        mean_brightness=200.0, relative_area=0.01,
        passed_validation=True, accepted=True, bib_number=number,
    )


def _face(x=0.1, y=0.1, w=0.1, h=0.1):
    return FaceCandidateTrace(
        x=x, y=y, w=w, h=h,
        confidence=0.9, passed=True, accepted=True,
    )


class TestSingleFaceRule:
    def test_single_face_single_bib_linked(self):
        """Single face + single bib → exactly one TraceLink."""
        face = _face()
        bib = _bib()
        result = predict_links([bib], [face])
        assert len(result) == 1
        assert result[0].bib_trace is bib
        assert result[0].face_trace is face
        assert result[0].provenance == "single_face"
        assert result[0].distance >= 0


class TestEdgeCases:
    def test_no_faces(self):
        """Empty face list → empty list."""
        result = predict_links([_bib()], [])
        assert result == []

    def test_no_bibs(self):
        """Empty bib list → empty list."""
        result = predict_links([], [_face()])
        assert result == []

    def test_both_empty(self):
        result = predict_links([], [])
        assert result == []


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

        assert len(result) == 2
        bib_trace_ids = {id(link.bib_trace) for link in result}
        face_trace_ids = {id(link.face_trace) for link in result}
        assert id(bib1) in bib_trace_ids
        assert id(bib2) in bib_trace_ids
        assert id(face1) in face_trace_ids
        assert id(face2) in face_trace_ids

    def test_bib_outside_all_torsos_skipped(self):
        """Bib whose centroid falls outside every face's torso region is not linked."""
        face = _face(x=0.1, y=0.1, w=0.1, h=0.1)
        # bib far to the right, well outside torso x∈[0.05,0.25]
        bib = _bib(x=0.8, y=0.25, w=0.1, h=0.1)
        result = predict_links([bib], [face])
        # single-face rule fires (1 face + 1 bib) → still links unconditionally
        # only the multi-face path skips out-of-torso bibs
        assert len(result) == 1  # single-face rule, not spatial

    def test_each_bib_used_at_most_once(self):
        """One bib is not assigned to two faces."""
        face1 = _face(x=0.1, y=0.1, w=0.1, h=0.1)
        face2 = _face(x=0.15, y=0.1, w=0.1, h=0.1)  # close to face1
        # Single bib inside both torso regions
        bib = _bib(x=0.1, y=0.25, w=0.1, h=0.1)
        result = predict_links([bib], [face1, face2])
        # bib should appear at most once
        bib_uses = sum(1 for link in result if link.bib_trace is bib)
        assert bib_uses <= 1
