"""TDD tests for benchmarking.scoring — IoU matching and scorecards."""

from __future__ import annotations

import pytest

from benchmarking.scoring import (
    compute_iou,
    match_boxes,
    MatchResult,
    BibScorecard,
    FaceScorecard,
    score_bibs,
    score_faces,
    format_scorecard,
)
from benchmarking.ground_truth import BibBox, FaceBox


# =============================================================================
# compute_iou
# =============================================================================


class TestComputeIou:
    """compute_iou takes two (x, y, w, h) boxes and returns IoU in [0, 1]."""

    def test_identical_boxes(self):
        box = (0.1, 0.2, 0.3, 0.4)
        assert compute_iou(box, box) == pytest.approx(1.0)

    def test_disjoint_boxes(self):
        a = (0.0, 0.0, 0.1, 0.1)
        b = (0.5, 0.5, 0.1, 0.1)
        assert compute_iou(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        # Two 1x1 boxes overlapping in a 0.5x1 strip
        a = (0.0, 0.0, 1.0, 1.0)
        b = (0.5, 0.0, 1.0, 1.0)
        # intersection = 0.5 * 1.0 = 0.5, union = 1.0 + 1.0 - 0.5 = 1.5
        assert compute_iou(a, b) == pytest.approx(0.5 / 1.5)

    def test_one_inside_other(self):
        outer = (0.0, 0.0, 1.0, 1.0)
        inner = (0.25, 0.25, 0.5, 0.5)
        # intersection = 0.25, union = 1.0 + 0.25 - 0.25 = 1.0
        assert compute_iou(outer, inner) == pytest.approx(0.25)

    def test_zero_area_box_returns_zero(self):
        a = (0.0, 0.0, 0.0, 0.0)
        b = (0.0, 0.0, 1.0, 1.0)
        assert compute_iou(a, b) == pytest.approx(0.0)

    def test_both_zero_area_returns_zero(self):
        a = (0.0, 0.0, 0.0, 0.0)
        assert compute_iou(a, a) == pytest.approx(0.0)

    def test_touching_edges_no_overlap(self):
        a = (0.0, 0.0, 0.5, 0.5)
        b = (0.5, 0.0, 0.5, 0.5)
        assert compute_iou(a, b) == pytest.approx(0.0)

    def test_symmetric(self):
        a = (0.1, 0.1, 0.3, 0.4)
        b = (0.2, 0.2, 0.5, 0.3)
        assert compute_iou(a, b) == pytest.approx(compute_iou(b, a))


# =============================================================================
# match_boxes
# =============================================================================


class TestMatchBoxes:
    """Greedy IoU matching: for each GT box, find best predicted box above
    threshold. Once matched, neither box can be reused."""

    def test_empty_predicted(self):
        result = match_boxes(predicted=[], ground_truth=[(0, 0, 1, 1)])
        assert result.tp == []
        assert result.fp == []
        assert result.fn == [0]

    def test_empty_ground_truth(self):
        result = match_boxes(predicted=[(0, 0, 1, 1)], ground_truth=[])
        assert result.tp == []
        assert result.fp == [0]
        assert result.fn == []

    def test_both_empty(self):
        result = match_boxes(predicted=[], ground_truth=[])
        assert result.tp == []
        assert result.fp == []
        assert result.fn == []

    def test_perfect_match(self):
        boxes = [(0.1, 0.1, 0.3, 0.3), (0.6, 0.6, 0.2, 0.2)]
        result = match_boxes(predicted=boxes, ground_truth=boxes)
        assert len(result.tp) == 2
        assert result.fp == []
        assert result.fn == []

    def test_no_match_below_threshold(self):
        a = (0.0, 0.0, 0.1, 0.1)
        b = (0.5, 0.5, 0.1, 0.1)  # disjoint
        result = match_boxes(predicted=[a], ground_truth=[b], iou_threshold=0.5)
        assert result.tp == []
        assert result.fp == [0]
        assert result.fn == [0]

    def test_threshold_boundary_exact(self):
        """Boxes with IoU exactly at threshold should match."""
        # Two 1x1 boxes overlapping in a 0.5x1 strip → IoU = 1/3
        a = (0.0, 0.0, 1.0, 1.0)
        b = (0.5, 0.0, 1.0, 1.0)
        iou = compute_iou(a, b)
        result = match_boxes(predicted=[a], ground_truth=[b], iou_threshold=iou)
        assert len(result.tp) == 1

    def test_greedy_picks_best_iou(self):
        """When multiple predicted boxes overlap a GT box, the best IoU wins."""
        gt = (0.0, 0.0, 1.0, 1.0)
        pred_good = (0.0, 0.0, 1.0, 1.0)  # IoU = 1.0
        pred_ok = (0.5, 0.0, 1.0, 1.0)    # IoU ≈ 0.33
        result = match_boxes(
            predicted=[pred_ok, pred_good], ground_truth=[gt], iou_threshold=0.3
        )
        assert len(result.tp) == 1
        # The better match (pred_good at index 1) should win
        matched_pred_idx = result.tp[0][0]
        assert matched_pred_idx == 1
        assert result.fp == [0]  # pred_ok is unmatched

    def test_one_to_one_matching(self):
        """Each GT box can only match one predicted box and vice versa."""
        gt1 = (0.0, 0.0, 0.5, 0.5)
        gt2 = (0.5, 0.5, 0.5, 0.5)
        pred1 = (0.0, 0.0, 0.5, 0.5)
        pred2 = (0.5, 0.5, 0.5, 0.5)
        result = match_boxes(
            predicted=[pred1, pred2], ground_truth=[gt1, gt2], iou_threshold=0.5
        )
        assert len(result.tp) == 2
        assert result.fp == []
        assert result.fn == []

    def test_more_predicted_than_gt(self):
        gt = [(0.0, 0.0, 0.5, 0.5)]
        pred = [(0.0, 0.0, 0.5, 0.5), (0.5, 0.5, 0.3, 0.3)]
        result = match_boxes(predicted=pred, ground_truth=gt, iou_threshold=0.5)
        assert len(result.tp) == 1
        assert len(result.fp) == 1
        assert result.fn == []

    def test_more_gt_than_predicted(self):
        gt = [(0.0, 0.0, 0.5, 0.5), (0.5, 0.5, 0.3, 0.3)]
        pred = [(0.0, 0.0, 0.5, 0.5)]
        result = match_boxes(predicted=pred, ground_truth=gt, iou_threshold=0.5)
        assert len(result.tp) == 1
        assert result.fp == []
        assert len(result.fn) == 1

    def test_match_result_counts(self):
        gt = [(0.0, 0.0, 0.5, 0.5), (0.5, 0.5, 0.3, 0.3)]
        pred = [(0.0, 0.0, 0.5, 0.5), (0.8, 0.8, 0.1, 0.1)]
        result = match_boxes(predicted=pred, ground_truth=gt, iou_threshold=0.5)
        assert result.tp_count == 1
        assert result.fp_count == 1
        assert result.fn_count == 1


# =============================================================================
# BibScorecard
# =============================================================================


class TestBibScorecard:
    """BibScorecard: detection P/R via IoU + OCR accuracy on matched boxes."""

    def test_perfect_detection_and_ocr(self):
        sc = BibScorecard(
            detection_tp=3, detection_fp=0, detection_fn=0,
            ocr_correct=3, ocr_total=3,
        )
        assert sc.detection_precision == pytest.approx(1.0)
        assert sc.detection_recall == pytest.approx(1.0)
        assert sc.detection_f1 == pytest.approx(1.0)
        assert sc.ocr_accuracy == pytest.approx(1.0)

    def test_no_detections(self):
        sc = BibScorecard(
            detection_tp=0, detection_fp=0, detection_fn=5,
            ocr_correct=0, ocr_total=0,
        )
        assert sc.detection_precision == pytest.approx(0.0)
        assert sc.detection_recall == pytest.approx(0.0)
        assert sc.detection_f1 == pytest.approx(0.0)
        assert sc.ocr_accuracy == pytest.approx(0.0)

    def test_mixed_results(self):
        sc = BibScorecard(
            detection_tp=2, detection_fp=1, detection_fn=1,
            ocr_correct=1, ocr_total=2,
        )
        assert sc.detection_precision == pytest.approx(2 / 3)
        assert sc.detection_recall == pytest.approx(2 / 3)
        assert sc.ocr_accuracy == pytest.approx(0.5)

    def test_all_false_positives(self):
        sc = BibScorecard(
            detection_tp=0, detection_fp=3, detection_fn=0,
            ocr_correct=0, ocr_total=0,
        )
        assert sc.detection_precision == pytest.approx(0.0)
        # No GT boxes → recall is 0 by convention
        assert sc.detection_recall == pytest.approx(0.0)

    def test_to_dict_round_trip(self):
        sc = BibScorecard(
            detection_tp=2, detection_fp=1, detection_fn=1,
            ocr_correct=1, ocr_total=2,
        )
        d = sc.to_dict()
        assert d["detection_tp"] == 2
        assert d["ocr_accuracy"] == pytest.approx(0.5)
        assert "detection_precision" in d
        assert "detection_f1" in d


# =============================================================================
# FaceScorecard
# =============================================================================


class TestFaceScorecard:
    """FaceScorecard: detection P/R via IoU for keep-scoped faces."""

    def test_perfect(self):
        sc = FaceScorecard(detection_tp=4, detection_fp=0, detection_fn=0)
        assert sc.detection_precision == pytest.approx(1.0)
        assert sc.detection_recall == pytest.approx(1.0)

    def test_empty(self):
        sc = FaceScorecard(detection_tp=0, detection_fp=0, detection_fn=0)
        assert sc.detection_precision == pytest.approx(0.0)
        assert sc.detection_recall == pytest.approx(0.0)

    def test_to_dict(self):
        sc = FaceScorecard(detection_tp=3, detection_fp=1, detection_fn=2)
        d = sc.to_dict()
        assert d["detection_tp"] == 3
        assert d["detection_precision"] == pytest.approx(3 / 4)
        assert d["detection_recall"] == pytest.approx(3 / 5)


# =============================================================================
# score_bibs — end-to-end scoring of bib detections against ground truth
# =============================================================================


class TestScoreBibs:
    """score_bibs takes predicted BibBoxes and GT BibBoxes, returns BibScorecard."""

    def test_perfect_detection_and_ocr(self):
        """Predicted boxes match GT boxes with correct numbers."""
        gt = [
            BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42"),
            BibBox(x=0.6, y=0.6, w=0.2, h=0.2, number="99"),
        ]
        pred = [
            BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42"),
            BibBox(x=0.6, y=0.6, w=0.2, h=0.2, number="99"),
        ]
        sc = score_bibs(pred, gt)
        assert sc.detection_tp == 2
        assert sc.detection_fp == 0
        assert sc.detection_fn == 0
        assert sc.ocr_correct == 2
        assert sc.ocr_total == 2

    def test_correct_detection_wrong_ocr(self):
        """Box matches but number is wrong → counted as detection TP but OCR miss."""
        gt = [BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42")]
        pred = [BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="43")]
        sc = score_bibs(pred, gt)
        assert sc.detection_tp == 1
        assert sc.ocr_correct == 0
        assert sc.ocr_total == 1

    def test_missed_gt_box(self):
        """GT box not detected → FN."""
        gt = [BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42")]
        sc = score_bibs([], gt)
        assert sc.detection_fn == 1
        assert sc.detection_tp == 0

    def test_extra_predicted_box(self):
        """Predicted box with no GT match → FP."""
        pred = [BibBox(x=0.5, y=0.5, w=0.2, h=0.2, number="99")]
        sc = score_bibs(pred, [])
        assert sc.detection_fp == 1
        assert sc.detection_tp == 0

    def test_gt_without_coords_skipped(self):
        """GT boxes with zero-area coords (legacy) are excluded from IoU scoring."""
        gt = [BibBox(x=0, y=0, w=0, h=0, number="42")]
        pred = [BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42")]
        sc = score_bibs(pred, gt)
        # No IoU matching possible — GT box has no coords
        assert sc.detection_tp == 0
        assert sc.detection_fn == 0  # zero-area GT excluded
        assert sc.detection_fp == 1  # predicted unmatched

    def test_not_bib_tag_excluded(self):
        """GT boxes tagged as 'not_bib' should be excluded from scoring."""
        gt = [
            BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42"),
            BibBox(x=0.5, y=0.5, w=0.2, h=0.2, number="0", tag="not_bib"),
        ]
        pred = [BibBox(x=0.1, y=0.1, w=0.3, h=0.2, number="42")]
        sc = score_bibs(pred, gt)
        assert sc.detection_tp == 1
        assert sc.detection_fn == 0  # not_bib GT excluded

    def test_both_empty(self):
        sc = score_bibs([], [])
        assert sc.detection_tp == 0
        assert sc.detection_fp == 0
        assert sc.detection_fn == 0
        assert sc.ocr_total == 0


# =============================================================================
# score_faces — end-to-end scoring of face detections
# =============================================================================


class TestScoreFaces:
    """score_faces takes predicted FaceBoxes and GT FaceBoxes, returns FaceScorecard."""

    def test_perfect_detection(self):
        gt = [
            FaceBox(x=0.1, y=0.1, w=0.15, h=0.2, scope="keep"),
            FaceBox(x=0.5, y=0.5, w=0.15, h=0.2, scope="keep"),
        ]
        pred = [
            FaceBox(x=0.1, y=0.1, w=0.15, h=0.2),
            FaceBox(x=0.5, y=0.5, w=0.15, h=0.2),
        ]
        sc = score_faces(pred, gt)
        assert sc.detection_tp == 2
        assert sc.detection_fp == 0
        assert sc.detection_fn == 0

    def test_ignore_scoped_gt_excluded(self):
        """GT faces with scope='ignore' should not count as FN."""
        gt = [
            FaceBox(x=0.1, y=0.1, w=0.15, h=0.2, scope="keep"),
            FaceBox(x=0.5, y=0.5, w=0.15, h=0.2, scope="ignore"),
        ]
        pred = [FaceBox(x=0.1, y=0.1, w=0.15, h=0.2)]
        sc = score_faces(pred, gt)
        assert sc.detection_tp == 1
        assert sc.detection_fn == 0  # ignore-scoped excluded

    def test_unknown_scoped_gt_excluded(self):
        """GT faces with scope='unknown' should be excluded from scoring."""
        gt = [FaceBox(x=0.1, y=0.1, w=0.15, h=0.2, scope="unknown")]
        pred = [FaceBox(x=0.1, y=0.1, w=0.15, h=0.2)]
        sc = score_faces(pred, gt)
        # unknown GT is not scored — pred becomes FP
        assert sc.detection_tp == 0
        assert sc.detection_fp == 1

    def test_gt_without_coords_skipped(self):
        """GT face boxes without coords should be excluded."""
        gt = [FaceBox(x=0, y=0, w=0, h=0, scope="keep")]
        pred = [FaceBox(x=0.1, y=0.1, w=0.15, h=0.2)]
        sc = score_faces(pred, gt)
        assert sc.detection_tp == 0
        assert sc.detection_fn == 0

    def test_both_empty(self):
        sc = score_faces([], [])
        assert sc.detection_tp == 0
        assert sc.detection_fp == 0
        assert sc.detection_fn == 0


# =============================================================================
# format_scorecard
# =============================================================================


class TestFormatScorecard:
    """format_scorecard returns a human-readable multi-line summary."""

    def test_bib_scorecard_format(self):
        sc = BibScorecard(
            detection_tp=5, detection_fp=2, detection_fn=1,
            ocr_correct=4, ocr_total=5,
        )
        text = format_scorecard(bib=sc)
        assert "Bib Detection" in text
        assert "Precision" in text
        assert "Recall" in text
        assert "OCR Accuracy" in text

    def test_face_scorecard_format(self):
        sc = FaceScorecard(detection_tp=3, detection_fp=1, detection_fn=2)
        text = format_scorecard(face=sc)
        assert "Face Detection" in text
        assert "Precision" in text

    def test_combined_format(self):
        bib = BibScorecard(
            detection_tp=5, detection_fp=2, detection_fn=1,
            ocr_correct=4, ocr_total=5,
        )
        face = FaceScorecard(detection_tp=3, detection_fp=1, detection_fn=2)
        text = format_scorecard(bib=bib, face=face)
        assert "Bib Detection" in text
        assert "Face Detection" in text

    def test_empty_scorecard_no_crash(self):
        text = format_scorecard()
        assert isinstance(text, str)
