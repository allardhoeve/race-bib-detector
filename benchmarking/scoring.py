"""IoU-based scoring utilities and scorecards for benchmark evaluation.

Provides:
- ``compute_iou``: IoU between two (x, y, w, h) boxes.
- ``match_boxes``: Greedy IoU matching returning TP/FP/FN.
- ``BibScorecard`` / ``FaceScorecard``: Aggregate detection metrics.
- ``score_bibs`` / ``score_faces``: End-to-end scoring helpers.
- ``format_scorecard``: Human-readable summary text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .ground_truth import BibBox, BibFaceLink, FaceBox, _BIB_BOX_UNSCORED

# Type alias for a box as (x, y, w, h) tuple
Box = tuple[float, float, float, float]


# =============================================================================
# IoU computation
# =============================================================================


def compute_iou(box_a: Box, box_b: Box) -> float:
    """Compute intersection-over-union between two (x, y, w, h) boxes.

    Uses normalised (x, y, w, h) format as used throughout the benchmarking schema.
    See also ``geometry.rect_iou`` for pixel-rect (x1, y1, x2, y2) format.

    Args:
        box_a: First box as (x, y, width, height).
        box_b: Second box as (x, y, width, height).

    Returns:
        IoU value in [0, 1]. Returns 0.0 for zero-area boxes.
    """
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    # Convert to (x1, y1, x2, y2)
    ax1, ay1, ax2, ay2 = ax, ay, ax + aw, ay + ah
    bx1, by1, bx2, by2 = bx, by, bx + bw, by + bh

    # Intersection
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = aw * ah
    area_b = bw * bh
    union = area_a + area_b - inter_area

    if union <= 0:
        return 0.0
    return inter_area / union


# =============================================================================
# Greedy box matching
# =============================================================================


@dataclass
class MatchResult:
    """Result of greedy IoU box matching.

    Attributes:
        tp: List of (predicted_index, ground_truth_index) matched pairs.
        fp: Indices of unmatched predicted boxes.
        fn: Indices of unmatched ground truth boxes.
    """

    tp: list[tuple[int, int]]
    fp: list[int]
    fn: list[int]

    @property
    def tp_count(self) -> int:
        return len(self.tp)

    @property
    def fp_count(self) -> int:
        return len(self.fp)

    @property
    def fn_count(self) -> int:
        return len(self.fn)


def match_boxes(
    predicted: Sequence[Box],
    ground_truth: Sequence[Box],
    iou_threshold: float = 0.5,
) -> MatchResult:
    """Greedy IoU matching between predicted and ground truth boxes.

    Algorithm: compute all pairwise IoU scores, then greedily assign matches
    from highest IoU downward. Each box can only be matched once.

    Args:
        predicted: Predicted boxes as (x, y, w, h) tuples.
        ground_truth: Ground truth boxes as (x, y, w, h) tuples.
        iou_threshold: Minimum IoU to count as a match (inclusive).

    Returns:
        MatchResult with tp pairs, fp indices, fn indices.
    """
    if not predicted and not ground_truth:
        return MatchResult(tp=[], fp=[], fn=[])

    if not predicted:
        return MatchResult(tp=[], fp=[], fn=list(range(len(ground_truth))))

    if not ground_truth:
        return MatchResult(tp=[], fp=list(range(len(predicted))), fn=[])

    # Compute all pairwise IoU scores
    pairs: list[tuple[float, int, int]] = []
    for pi, pbox in enumerate(predicted):
        for gi, gbox in enumerate(ground_truth):
            iou = compute_iou(pbox, gbox)
            if iou >= iou_threshold:
                pairs.append((iou, pi, gi))

    # Sort by IoU descending (greedy: best matches first)
    pairs.sort(key=lambda t: t[0], reverse=True)

    matched_pred: set[int] = set()
    matched_gt: set[int] = set()
    tp: list[tuple[int, int]] = []

    for _iou, pi, gi in pairs:
        if pi in matched_pred or gi in matched_gt:
            continue
        tp.append((pi, gi))
        matched_pred.add(pi)
        matched_gt.add(gi)

    fp = [i for i in range(len(predicted)) if i not in matched_pred]
    fn = [i for i in range(len(ground_truth)) if i not in matched_gt]

    return MatchResult(tp=tp, fp=fp, fn=fn)


# =============================================================================
# Scorecards
# =============================================================================


def _safe_div(num: float, denom: float) -> float:
    """Division returning 0.0 when denominator is zero."""
    return num / denom if denom > 0 else 0.0


@dataclass
class BibScorecard:
    """Bib detection scorecard: IoU-based detection P/R + OCR accuracy.

    Attributes:
        detection_tp: Matched predicted/GT box pairs (IoU >= threshold).
        detection_fp: Predicted boxes with no GT match.
        detection_fn: GT boxes with no predicted match.
        ocr_correct: Matched pairs where bib number is correct.
        ocr_total: Total matched pairs (= detection_tp).
    """

    detection_tp: int
    detection_fp: int
    detection_fn: int
    ocr_correct: int
    ocr_total: int

    @property
    def detection_precision(self) -> float:
        return _safe_div(self.detection_tp, self.detection_tp + self.detection_fp)

    @property
    def detection_recall(self) -> float:
        return _safe_div(self.detection_tp, self.detection_tp + self.detection_fn)

    @property
    def detection_f1(self) -> float:
        p, r = self.detection_precision, self.detection_recall
        return _safe_div(2 * p * r, p + r)

    @property
    def ocr_accuracy(self) -> float:
        return _safe_div(self.ocr_correct, self.ocr_total)

    def to_dict(self) -> dict:
        return {
            "detection_tp": self.detection_tp,
            "detection_fp": self.detection_fp,
            "detection_fn": self.detection_fn,
            "detection_precision": self.detection_precision,
            "detection_recall": self.detection_recall,
            "detection_f1": self.detection_f1,
            "ocr_correct": self.ocr_correct,
            "ocr_total": self.ocr_total,
            "ocr_accuracy": self.ocr_accuracy,
        }


@dataclass
class FaceScorecard:
    """Face detection scorecard: IoU-based detection P/R for keep-scoped faces.

    Attributes:
        detection_tp: Matched predicted/GT box pairs.
        detection_fp: Predicted boxes with no GT match.
        detection_fn: GT boxes with no predicted match.
    """

    detection_tp: int
    detection_fp: int
    detection_fn: int

    @property
    def detection_precision(self) -> float:
        return _safe_div(self.detection_tp, self.detection_tp + self.detection_fp)

    @property
    def detection_recall(self) -> float:
        return _safe_div(self.detection_tp, self.detection_tp + self.detection_fn)

    @property
    def detection_f1(self) -> float:
        p, r = self.detection_precision, self.detection_recall
        return _safe_div(2 * p * r, p + r)

    def to_dict(self) -> dict:
        return {
            "detection_tp": self.detection_tp,
            "detection_fp": self.detection_fp,
            "detection_fn": self.detection_fn,
            "detection_precision": self.detection_precision,
            "detection_recall": self.detection_recall,
            "detection_f1": self.detection_f1,
        }


@dataclass
class LinkScorecard:
    """Bib-face link association scorecard.

    A TP requires: predicted bib box matches GT bib box (IoU >= threshold),
    predicted face box matches GT face box (IoU >= threshold), AND the GT
    link between those boxes exists.

    Attributes:
        link_tp: Correctly predicted links.
        link_fp: Predicted links with no matching GT link.
        link_fn: GT links with no matching predicted link.
        gt_link_count: Total GT links (for reference even when pipeline
                       provides no predictions).
    """

    link_tp: int
    link_fp: int
    link_fn: int
    gt_link_count: int

    @property
    def link_precision(self) -> float:
        return _safe_div(self.link_tp, self.link_tp + self.link_fp)

    @property
    def link_recall(self) -> float:
        return _safe_div(self.link_tp, self.link_tp + self.link_fn)

    @property
    def link_f1(self) -> float:
        p, r = self.link_precision, self.link_recall
        return _safe_div(2 * p * r, p + r)

    def to_dict(self) -> dict:
        return {
            "link_tp": self.link_tp,
            "link_fp": self.link_fp,
            "link_fn": self.link_fn,
            "link_f1": self.link_f1,
            "link_precision": self.link_precision,
            "link_recall": self.link_recall,
            "gt_link_count": self.gt_link_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LinkScorecard:
        return cls(
            link_tp=data["link_tp"],
            link_fp=data["link_fp"],
            link_fn=data["link_fn"],
            gt_link_count=data["gt_link_count"],
        )


# =============================================================================
# End-to-end scoring helpers
# =============================================================================


def _bibbox_to_tuple(b: BibBox) -> Box:
    return (b.x, b.y, b.w, b.h)


def _facebox_to_tuple(b: FaceBox) -> Box:
    return (b.x, b.y, b.w, b.h)


def score_bibs(
    predicted: Sequence[BibBox],
    ground_truth: Sequence[BibBox],
    iou_threshold: float = 0.5,
) -> BibScorecard:
    """Score bib detections against ground truth.

    Scope scoring rules:

    - ``bib``: expected to be found. Missed = FN, found = TP.
    - ``bib_clipped``: scored the same as ``bib`` (stretch goal — may be
      reported separately in future).
    - ``not_bib``: not a real bib — excluded from GT before matching.
    - ``bib_obscured``: real bib but unreadable — excluded from GT.

    Note: excluded GT boxes become "don't care" regions. In theory a
    prediction overlapping an excluded box would be counted as FP (since
    the GT box is absent from matching). In practice this doesn't occur
    because the detector rarely fires on non-bib / obscured regions.

    Additional filters:
    - GT boxes with ``has_coords == False`` (zero-area, legacy) are excluded.

    After IoU matching, OCR accuracy is computed on matched pairs by comparing
    the ``number`` field (string equality, stripped).

    Args:
        predicted: Predicted bib boxes (from detection pipeline).
        ground_truth: Ground truth bib boxes.
        iou_threshold: Minimum IoU for a match.

    Returns:
        BibScorecard with detection and OCR metrics.
    """
    # Filter GT: only boxes with coords and scored scopes
    gt_filtered = [
        b for b in ground_truth
        if b.has_coords and b.scope not in _BIB_BOX_UNSCORED
    ]

    # Filter predicted: only boxes with coords
    pred_filtered = [b for b in predicted if b.has_coords]

    pred_tuples = [_bibbox_to_tuple(b) for b in pred_filtered]
    gt_tuples = [_bibbox_to_tuple(b) for b in gt_filtered]

    result = match_boxes(pred_tuples, gt_tuples, iou_threshold)

    # OCR accuracy on matched pairs
    ocr_correct = 0
    for pi, gi in result.tp:
        if pred_filtered[pi].number.strip() == gt_filtered[gi].number.strip():
            ocr_correct += 1

    return BibScorecard(
        detection_tp=result.tp_count,
        detection_fp=result.fp_count,
        detection_fn=result.fn_count,
        ocr_correct=ocr_correct,
        ocr_total=result.tp_count,
    )


def score_faces(
    predicted: Sequence[FaceBox],
    ground_truth: Sequence[FaceBox],
    iou_threshold: float = 0.5,
) -> FaceScorecard:
    """Score face detections against ground truth.

    Only ``keep``-scoped GT boxes with coords are included in scoring.
    ``exclude`` and ``uncertain`` scoped GT boxes are excluded entirely.

    Args:
        predicted: Predicted face boxes (from detection pipeline).
        ground_truth: Ground truth face boxes.
        iou_threshold: Minimum IoU for a match.

    Returns:
        FaceScorecard with detection metrics.
    """
    # Filter GT: only keep-scoped boxes with coords
    gt_filtered = [b for b in ground_truth if b.scope == "keep" and b.has_coords]

    # Filter predicted: only boxes with coords
    pred_filtered = [b for b in predicted if b.has_coords]

    pred_tuples = [_facebox_to_tuple(b) for b in pred_filtered]
    gt_tuples = [_facebox_to_tuple(b) for b in gt_filtered]

    result = match_boxes(pred_tuples, gt_tuples, iou_threshold)

    return FaceScorecard(
        detection_tp=result.tp_count,
        detection_fp=result.fp_count,
        detection_fn=result.fn_count,
    )


def score_links(
    predicted_pairs: Sequence[tuple[BibBox, FaceBox]],
    gt_bib_boxes: Sequence[BibBox],
    gt_face_boxes: Sequence[FaceBox],
    gt_links: Sequence[BibFaceLink],
    bib_iou_threshold: float = 0.5,
    face_iou_threshold: float = 0.5,
) -> LinkScorecard:
    """Score predicted bib-face links against ground truth links.

    Each predicted pair is a (bib_box, face_box) tuple from the pipeline.
    A pair is a TP only if:
      - its bib_box matches a GT bib box at >= bib_iou_threshold,
      - its face_box matches a GT face box at >= face_iou_threshold, AND
      - the GT link (gt_bib_index, gt_face_index) between those boxes exists.

    Args:
        predicted_pairs: (bib_box, face_box) pairs from the detection pipeline.
        gt_bib_boxes: GT bib boxes for this photo, in index order matching
                      BibFaceLink.bib_index.
        gt_face_boxes: GT face boxes for this photo, in index order matching
                       BibFaceLink.face_index.
        gt_links: GT links for this photo.
        bib_iou_threshold: Min IoU to consider a bib box matched.
        face_iou_threshold: Min IoU to consider a face box matched.

    Returns:
        LinkScorecard with TP/FP/FN counts and gt_link_count.
    """
    gt_link_count = len(gt_links)

    if not predicted_pairs:
        return LinkScorecard(
            link_tp=0, link_fp=0, link_fn=gt_link_count,
            gt_link_count=gt_link_count,
        )

    if not gt_links:
        return LinkScorecard(
            link_tp=0, link_fp=len(predicted_pairs), link_fn=0,
            gt_link_count=0,
        )

    # Step 1: match predicted bib boxes to GT bib boxes
    pred_bib_tuples = [_bibbox_to_tuple(p[0]) for p in predicted_pairs]
    gt_bib_tuples = [_bibbox_to_tuple(b) for b in gt_bib_boxes]
    bib_match = match_boxes(pred_bib_tuples, gt_bib_tuples, bib_iou_threshold)
    pred_to_gt_bib: dict[int, int] = {pi: gi for pi, gi in bib_match.tp}

    # Step 2: match predicted face boxes to GT face boxes
    pred_face_tuples = [_facebox_to_tuple(p[1]) for p in predicted_pairs]
    gt_face_tuples = [_facebox_to_tuple(b) for b in gt_face_boxes]
    face_match = match_boxes(pred_face_tuples, gt_face_tuples, face_iou_threshold)
    pred_to_gt_face: dict[int, int] = {pi: gi for pi, gi in face_match.tp}

    # Step 3: build GT link set for O(1) lookup
    gt_link_set = {(lnk.bib_index, lnk.face_index) for lnk in gt_links}

    # Step 4: for each predicted pair, check if both boxes matched and link exists
    matched_gt_links: set[tuple[int, int]] = set()
    tp = fp = 0
    for pi in range(len(predicted_pairs)):
        gt_bib_idx = pred_to_gt_bib.get(pi)
        gt_face_idx = pred_to_gt_face.get(pi)
        if gt_bib_idx is not None and gt_face_idx is not None:
            pair = (gt_bib_idx, gt_face_idx)
            if pair in gt_link_set:
                tp += 1
                matched_gt_links.add(pair)
                continue
        fp += 1

    fn = len(gt_link_set - matched_gt_links)
    return LinkScorecard(link_tp=tp, link_fp=fp, link_fn=fn, gt_link_count=gt_link_count)


# =============================================================================
# Scorecard formatting
# =============================================================================


def format_scorecard(
    bib: BibScorecard | None = None,
    face: FaceScorecard | None = None,
    link: LinkScorecard | None = None,
) -> str:
    """Format scorecard(s) as human-readable text for terminal output.

    Args:
        bib: Optional bib scorecard.
        face: Optional face scorecard.
        link: Optional link scorecard.

    Returns:
        Multi-line string suitable for printing.
    """
    lines: list[str] = []

    if bib is not None:
        lines.append("Bib Detection")
        lines.append(f"  Precision: {bib.detection_precision:.1%}")
        lines.append(f"  Recall:    {bib.detection_recall:.1%}")
        lines.append(f"  F1:        {bib.detection_f1:.1%}")
        lines.append(f"  TP: {bib.detection_tp}  FP: {bib.detection_fp}  FN: {bib.detection_fn}")
        lines.append(f"  OCR Accuracy: {bib.ocr_accuracy:.1%} ({bib.ocr_correct}/{bib.ocr_total})")

    if face is not None:
        if lines:
            lines.append("")
        lines.append("Face Detection (keep-scoped)")
        lines.append(f"  Precision: {face.detection_precision:.1%}")
        lines.append(f"  Recall:    {face.detection_recall:.1%}")
        lines.append(f"  F1:        {face.detection_f1:.1%}")
        lines.append(f"  TP: {face.detection_tp}  FP: {face.detection_fp}  FN: {face.detection_fn}")

    if link is not None:
        if lines:
            lines.append("")
        lines.append("Bib-Face Links")
        lines.append(f"  GT links:  {link.gt_link_count}")
        if link.gt_link_count > 0 or link.link_fp > 0:
            lines.append(f"  TP: {link.link_tp}  FP: {link.link_fp}  FN: {link.link_fn}")
            lines.append(f"  Precision: {link.link_precision:.1%}")
            lines.append(f"  Recall:    {link.link_recall:.1%}")
            lines.append(f"  F1:        {link.link_f1:.1%}")
        else:
            lines.append("  (no GT links yet)")

    return "\n".join(lines)
