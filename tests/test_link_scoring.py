"""Tests for LinkScorecard and score_links() (rewritten for TraceLink in task-095)."""

import pytest

from pipeline.types import BibCandidateTrace, BibFaceLink, FaceCandidateTrace, FaceLabel, BibLabel, TraceLink
from benchmarking.scoring import LinkScorecard, score_links


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bib_label(x, y, w, h, number="1"):
    return BibLabel(x=x, y=y, w=w, h=h, number=number)


def _face_label(x, y, w, h):
    return FaceLabel(x=x, y=y, w=w, h=h, scope="keep")


def _bib_trace(x, y, w, h, number="1"):
    return BibCandidateTrace(
        x=x, y=y, w=w, h=h,
        area=100, aspect_ratio=1.0, median_brightness=200.0,
        mean_brightness=200.0, relative_area=0.01,
        passed_validation=True, accepted=True, bib_number=number,
    )


def _face_trace(x, y, w, h):
    return FaceCandidateTrace(
        x=x, y=y, w=w, h=h,
        confidence=0.9, passed=True, accepted=True,
    )


def _link(bib_idx, face_idx):
    return BibFaceLink(bib_index=bib_idx, face_index=face_idx)


def _trace_link(bib, face, provenance="spatial"):
    bib_cx = bib.x + bib.w / 2
    bib_cy = bib.y + bib.h / 2
    face_cx = face.x + face.w / 2
    face_cy = face.y + face.h / 2
    dist = ((bib_cx - face_cx) ** 2 + (bib_cy - face_cy) ** 2) ** 0.5
    return TraceLink(face_trace=face, bib_trace=bib, provenance=provenance, distance=dist)


# ---------------------------------------------------------------------------
# score_links tests
# ---------------------------------------------------------------------------

class TestScoreLinks:
    def test_empty_predictions(self):
        """No predictions, N GT links → FN=N, TP=FP=0."""
        gt_bibs = [_bib_label(0.1, 0.1, 0.2, 0.2), _bib_label(0.5, 0.5, 0.2, 0.2)]
        gt_faces = [_face_label(0.3, 0.3, 0.1, 0.1)]
        gt_links = [_link(0, 0), _link(1, 0)]

        sc = score_links([], gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 0
        assert sc.link_fp == 0
        assert sc.link_fn == 2
        assert sc.gt_link_count == 2

    def test_empty_gt(self):
        """N predictions, no GT links → FP=N, TP=FN=0."""
        bt = _bib_trace(0.1, 0.1, 0.2, 0.2)
        ft = _face_trace(0.3, 0.3, 0.1, 0.1)
        pred = [_trace_link(bt, ft), _trace_link(bt, ft)]

        sc = score_links(pred, [_bib_label(0.1, 0.1, 0.2, 0.2)], [_face_label(0.3, 0.3, 0.1, 0.1)], [])

        assert sc.link_tp == 0
        assert sc.link_fp == 2
        assert sc.link_fn == 0
        assert sc.gt_link_count == 0

    def test_perfect_match(self):
        """Predictions exactly match GT links → TP=N, FP=FN=0."""
        bt0 = _bib_trace(0.1, 0.1, 0.2, 0.2)
        ft0 = _face_trace(0.4, 0.4, 0.15, 0.15)
        bt1 = _bib_trace(0.6, 0.6, 0.2, 0.2)
        ft1 = _face_trace(0.7, 0.1, 0.1, 0.1)

        gt_bibs = [_bib_label(0.1, 0.1, 0.2, 0.2), _bib_label(0.6, 0.6, 0.2, 0.2)]
        gt_faces = [_face_label(0.4, 0.4, 0.15, 0.15), _face_label(0.7, 0.1, 0.1, 0.1)]
        gt_links = [_link(0, 0), _link(1, 1)]

        pred = [_trace_link(bt0, ft0), _trace_link(bt1, ft1)]
        sc = score_links(pred, gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 2
        assert sc.link_fp == 0
        assert sc.link_fn == 0
        assert sc.gt_link_count == 2

    def test_wrong_pair(self):
        """Boxes match but link direction is wrong → FP."""
        bt0 = _bib_trace(0.1, 0.1, 0.2, 0.2)
        bt1 = _bib_trace(0.6, 0.6, 0.2, 0.2)
        ft0 = _face_trace(0.4, 0.4, 0.15, 0.15)
        ft1 = _face_trace(0.7, 0.1, 0.1, 0.1)

        gt_bibs = [_bib_label(0.1, 0.1, 0.2, 0.2), _bib_label(0.6, 0.6, 0.2, 0.2)]
        gt_faces = [_face_label(0.4, 0.4, 0.15, 0.15), _face_label(0.7, 0.1, 0.1, 0.1)]
        gt_links = [_link(0, 0), _link(1, 1)]  # bib0↔face0, bib1↔face1

        # Predicted pairs are swapped: bib0↔face1, bib1↔face0
        pred = [_trace_link(bt0, ft1), _trace_link(bt1, ft0)]
        sc = score_links(pred, gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 0
        assert sc.link_fp == 2
        assert sc.link_fn == 2

    def test_iou_below_threshold(self):
        """Boxes don't meet IoU threshold → pair counts as FP; GT link as FN."""
        gt_bib = _bib_label(0.1, 0.1, 0.2, 0.2)
        pred_bt = _bib_trace(0.8, 0.8, 0.1, 0.1)  # IoU ≈ 0 with gt_bib
        ft = _face_trace(0.4, 0.4, 0.15, 0.15)

        gt_links = [_link(0, 0)]
        pred = [_trace_link(pred_bt, ft)]

        sc = score_links(pred, [gt_bib], [_face_label(0.4, 0.4, 0.15, 0.15)], gt_links)

        assert sc.link_tp == 0
        assert sc.link_fp == 1
        assert sc.link_fn == 1


# ---------------------------------------------------------------------------
# LinkScorecard property tests
# ---------------------------------------------------------------------------

class TestLinkScorecardProperties:
    def test_precision_recall_f1(self):
        sc = LinkScorecard(link_tp=2, link_fp=1, link_fn=1, gt_link_count=3)
        assert sc.link_precision == pytest.approx(2 / 3)
        assert sc.link_recall == pytest.approx(2 / 3)
        assert sc.link_f1 == pytest.approx(2 / 3)

    def test_zero_division_safe(self):
        sc = LinkScorecard(link_tp=0, link_fp=0, link_fn=0, gt_link_count=0)
        assert sc.link_precision == 0.0
        assert sc.link_recall == 0.0
        assert sc.link_f1 == 0.0

    def test_to_dict_keys(self):
        sc = LinkScorecard(link_tp=1, link_fp=2, link_fn=3, gt_link_count=4)
        d = sc.to_dict()
        for key in ("link_tp", "link_fp", "link_fn", "link_f1",
                    "link_precision", "link_recall", "gt_link_count"):
            assert key in d

    def test_from_dict_roundtrip(self):
        sc = LinkScorecard(link_tp=3, link_fp=1, link_fn=2, gt_link_count=5)
        sc2 = LinkScorecard.from_dict(sc.to_dict())
        assert sc2.link_tp == sc.link_tp
        assert sc2.link_fp == sc.link_fp
        assert sc2.link_fn == sc.link_fn
        assert sc2.gt_link_count == sc.gt_link_count
