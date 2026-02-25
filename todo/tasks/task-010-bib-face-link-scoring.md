# Task 010: Bib-face link scoring

Step 5 (part 4/4) + Step 6 link metric. Depends on task-007 (schema).
Independent of task-009 (UI) — scoring does not require the UI to be done.

## Goal

Add a `LinkScorecard` to `scoring.py` and wire it into `runner.py` so that
`bnr benchmark run` reports link accuracy alongside bib/face detection metrics.

## Background

A predicted link `(predicted_bib_box, predicted_face_box)` is a true positive if:
1. The predicted bib box matches a GT bib box at IoU >= threshold.
2. The predicted face box matches a GT face box at IoU >= threshold.
3. The GT link `(gt_bib_index, gt_face_index)` exists between those GT boxes.

This requires the detection pipeline to return its detected bib-face pairs —
currently it does not. Until the pipeline is extended, `score_links()` is a pure
GT-side utility that can be used once the pipeline provides link predictions.

**For the benchmark runner**: compute the GT link count and stub out link
scoring with zeroed metrics until the pipeline provides predictions. This adds
the infrastructure without blocking on pipeline work.

## Changes to `benchmarking/scoring.py`

### New dataclass: `LinkScorecard`

Add after `FaceScorecard`. Includes `from_dict()` for symmetry with how
`BenchmarkRun.from_dict()` reconstructs scorecards.

```python
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
```

### New function: `score_links()`

Add `BibFaceLink` to the existing import from `.ground_truth`.

```python
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
    # pred_to_gt_bib[pred_idx] = gt_bib_idx (only for matched predicted boxes)
    pred_to_gt_bib: dict[int, int] = {pi: gi for pi, gi in bib_match.tp}

    # Step 2: match predicted face boxes to GT face boxes
    pred_face_tuples = [_facebox_to_tuple(p[1]) for p in predicted_pairs]
    gt_face_tuples = [_facebox_to_tuple(b) for b in gt_face_boxes]
    face_match = match_boxes(pred_face_tuples, gt_face_tuples, face_iou_threshold)
    pred_to_gt_face: dict[int, int] = {pi: gi for pi, gi in face_match.tp}

    # Step 3: build a set of GT links as (gt_bib_idx, gt_face_idx) for O(1) lookup
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
```

### `format_scorecard()` update

Add `link: LinkScorecard | None = None` parameter. The full updated function:

```python
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
```

All existing callers pass `bib=` and/or `face=` as keyword arguments; `link` defaults
to `None` so there are no breaking changes.

## Changes to `benchmarking/runner.py`

### Add `face_scorecard` and `link_scorecard` to `BenchmarkRun`

`face_scorecard` is not yet in the dataclass — add it alongside `link_scorecard`:

```python
@dataclass
class BenchmarkRun:
    metadata: RunMetadata
    metrics: BenchmarkMetrics
    photo_results: list[PhotoResult]
    bib_scorecard: BibScorecard | None = None
    face_scorecard: FaceScorecard | None = None   # ← add
    link_scorecard: LinkScorecard | None = None   # ← add
```

Add the necessary import at the top of `runner.py`:

```python
from .scoring import BibScorecard, FaceScorecard, LinkScorecard, ...
```

### Update `BenchmarkRun.to_dict()`

```python
def to_dict(self) -> dict:
    d = {
        "metadata": self.metadata.to_dict(),
        "metrics": self.metrics.to_dict(),
        "photo_results": [r.to_dict() for r in self.photo_results],
    }
    if self.bib_scorecard is not None:
        d["bib_scorecard"] = self.bib_scorecard.to_dict()
    if self.face_scorecard is not None:
        d["face_scorecard"] = self.face_scorecard.to_dict()
    if self.link_scorecard is not None:
        d["link_scorecard"] = self.link_scorecard.to_dict()
    return d
```

### Update `BenchmarkRun.from_dict()`

```python
@classmethod
def from_dict(cls, data: dict) -> BenchmarkRun:
    bib_scorecard = None
    if "bib_scorecard" in data:
        sc = data["bib_scorecard"]
        bib_scorecard = BibScorecard(
            detection_tp=sc["detection_tp"],
            detection_fp=sc["detection_fp"],
            detection_fn=sc["detection_fn"],
            ocr_correct=sc["ocr_correct"],
            ocr_total=sc["ocr_total"],
        )

    face_scorecard = None
    if "face_scorecard" in data:
        sc = data["face_scorecard"]
        face_scorecard = FaceScorecard(
            detection_tp=sc["detection_tp"],
            detection_fp=sc["detection_fp"],
            detection_fn=sc["detection_fn"],
        )

    link_scorecard = None
    if "link_scorecard" in data:
        link_scorecard = LinkScorecard.from_dict(data["link_scorecard"])

    return cls(
        metadata=RunMetadata.from_dict(data["metadata"]),
        metrics=BenchmarkMetrics.from_dict(data["metrics"]),
        photo_results=[PhotoResult.from_dict(r) for r in data["photo_results"]],
        bib_scorecard=bib_scorecard,
        face_scorecard=face_scorecard,
        link_scorecard=link_scorecard,
    )
```

### Compute link scorecard in `run_benchmark()`

At the end of `run_benchmark()`, after the existing `bib_scorecard` computation:

```python
from .ground_truth import load_link_ground_truth

link_gt = load_link_ground_truth()

# Stub: pipeline does not yet provide link predictions.
# Count GT links for reporting; TP/FP = 0 until pipeline is extended.
total_gt_links = sum(
    len(link_gt.get_links(r.content_hash))
    for r in photo_results
)
benchmark_run.link_scorecard = LinkScorecard(
    link_tp=0,
    link_fp=0,
    link_fn=total_gt_links,
    gt_link_count=total_gt_links,
)
```

Note: `benchmark_run` is the variable name used at the end of `run_benchmark()` where
`bib_scorecard` is already assigned. Assign to `benchmark_run.link_scorecard` in place.

### Print link scorecard in `cmd_benchmark()` in `cli.py`

After the IoU scorecard print block:

```python
if run.link_scorecard and run.link_scorecard.gt_link_count > 0:
    from benchmarking.scoring import format_scorecard
    print(f"\n{format_scorecard(link=run.link_scorecard)}")
```

## Tests

Add `tests/test_link_scoring.py`:

- `test_score_links_empty_predictions()` — no predictions, N GT links → FN=N, TP=FP=0.
- `test_score_links_empty_gt()` — N predictions, no GT links → FP=N, TP=FN=0.
- `test_score_links_perfect_match()` — predictions exactly match GT links → TP=N, FP=FN=0.
- `test_score_links_wrong_pair()` — boxes match but link direction is wrong → FP.
- `test_score_links_iou_below_threshold()` — boxes don't meet IoU threshold → FP + FN.
- `test_link_scorecard_properties()` — verify precision/recall/f1 math.
- `test_link_scorecard_to_dict()` — verify all expected keys present.
- `test_link_scorecard_from_dict_roundtrip()` — `to_dict()` then `from_dict()` is identity.

## Scope boundaries

- **In scope**: `LinkScorecard` (with `from_dict`), `score_links()`, adding `face_scorecard`
  + `link_scorecard` fields to `BenchmarkRun`, stub integration in runner, CLI output, tests.
- **Out of scope**: pipeline changes to return link predictions, UI (task-009), schema
  (task-007 must be done first).
- `format_scorecard` signature change must be backward-compatible (new `link` param defaults to `None`).
- `FaceScorecard` itself already exists in `scoring.py`; `face_scorecard` is just missing
  from `BenchmarkRun` and is added here for completeness.
