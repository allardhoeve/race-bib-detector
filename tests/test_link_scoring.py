"""Tests for LinkScorecard and score_links()."""

import pytest

from benchmarking.ground_truth import BibBox, BibFaceLink, FaceBox
from benchmarking.scoring import LinkScorecard, score_links


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bib(x, y, w, h, number="1"):
    return BibBox(x=x, y=y, w=w, h=h, number=number)


def _face(x, y, w, h):
    return FaceBox(x=x, y=y, w=w, h=h, scope="keep")


def _link(bib_idx, face_idx):
    return BibFaceLink(bib_index=bib_idx, face_index=face_idx)


# ---------------------------------------------------------------------------
# score_links tests
# ---------------------------------------------------------------------------

class TestScoreLinks:
    def test_empty_predictions(self):
        """No predictions, N GT links → FN=N, TP=FP=0."""
        gt_bibs = [_bib(0.1, 0.1, 0.2, 0.2), _bib(0.5, 0.5, 0.2, 0.2)]
        gt_faces = [_face(0.3, 0.3, 0.1, 0.1)]
        gt_links = [_link(0, 0), _link(1, 0)]

        sc = score_links([], gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 0
        assert sc.link_fp == 0
        assert sc.link_fn == 2
        assert sc.gt_link_count == 2

    def test_empty_gt(self):
        """N predictions, no GT links → FP=N, TP=FN=0."""
        pred_bib = _bib(0.1, 0.1, 0.2, 0.2)
        pred_face = _face(0.3, 0.3, 0.1, 0.1)
        pairs = [(pred_bib, pred_face), (pred_bib, pred_face)]

        sc = score_links(pairs, [pred_bib], [pred_face], [])

        assert sc.link_tp == 0
        assert sc.link_fp == 2
        assert sc.link_fn == 0
        assert sc.gt_link_count == 0

    def test_perfect_match(self):
        """Predictions exactly match GT links → TP=N, FP=FN=0."""
        bib0 = _bib(0.1, 0.1, 0.2, 0.2)
        face0 = _face(0.4, 0.4, 0.15, 0.15)
        bib1 = _bib(0.6, 0.6, 0.2, 0.2)
        face1 = _face(0.7, 0.1, 0.1, 0.1)

        gt_bibs = [bib0, bib1]
        gt_faces = [face0, face1]
        gt_links = [_link(0, 0), _link(1, 1)]

        # Predicted pairs are the same boxes (IoU = 1.0)
        pairs = [(bib0, face0), (bib1, face1)]
        sc = score_links(pairs, gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 2
        assert sc.link_fp == 0
        assert sc.link_fn == 0
        assert sc.gt_link_count == 2

    def test_wrong_pair(self):
        """Boxes match but link direction is wrong → FP."""
        bib0 = _bib(0.1, 0.1, 0.2, 0.2)
        bib1 = _bib(0.6, 0.6, 0.2, 0.2)
        face0 = _face(0.4, 0.4, 0.15, 0.15)
        face1 = _face(0.7, 0.1, 0.1, 0.1)

        gt_bibs = [bib0, bib1]
        gt_faces = [face0, face1]
        gt_links = [_link(0, 0), _link(1, 1)]  # bib0↔face0, bib1↔face1

        # Predicted pairs are swapped: bib0↔face1, bib1↔face0
        pairs = [(bib0, face1), (bib1, face0)]
        sc = score_links(pairs, gt_bibs, gt_faces, gt_links)

        assert sc.link_tp == 0
        assert sc.link_fp == 2
        assert sc.link_fn == 2

    def test_iou_below_threshold(self):
        """Boxes don't meet IoU threshold → pair counts as FP; GT link as FN."""
        # GT bib at [0.1, 0.1, 0.2, 0.2]; predicted bib is far away
        gt_bib = _bib(0.1, 0.1, 0.2, 0.2)
        pred_bib = _bib(0.8, 0.8, 0.1, 0.1)  # IoU ≈ 0 with gt_bib
        face = _face(0.4, 0.4, 0.15, 0.15)

        gt_links = [_link(0, 0)]
        pairs = [(pred_bib, face)]

        sc = score_links(pairs, [gt_bib], [face], gt_links)

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
