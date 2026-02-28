# Face Detection Tuning

This document explains the tunable parameters for face detection, what each one does,
where it lives in the code, and how changing it affects detection quality.

---

## Concepts and acronyms

### Detection and filtering

**Confidence score**
A number between 0 and 1 that the neural network assigns to each candidate box,
expressing how certain it is that the region contains a face. A score of 0.9 means
"very likely a face"; 0.1 means "barely above noise."

**NMS — Non-Maximum Suppression**
When a detector slides a window across an image it often fires multiple overlapping
boxes on the same face. NMS is a post-processing step that keeps only the
highest-confidence box and discards the others if they overlap too much.
"How much is too much" is controlled by the IoU threshold.

**IoU — Intersection over Union**
A measure of how much two boxes overlap.
`IoU = area_of_intersection / area_of_union`.
A value of 1.0 means the boxes are identical; 0.0 means they do not overlap at all.
Used in two distinct places:
- During NMS (to decide whether to suppress a duplicate box).
- During scoring (to decide whether a predicted box matches a ground-truth box).

**Haar cascade**
An older, fast, CPU-based face detector. It scans the image at multiple scales using
a set of hand-crafted features ("Haar features"). Less accurate than a neural network
but requires no GPU and no deep-learning model file.

**DNN SSD — Deep Neural Network, Single Shot Detector**
The primary face detector. A pre-trained convolutional neural network (ResNet-10 backbone,
300×300 input) that detects faces in a single forward pass without a separate region
proposal step. More accurate than Haar, especially on partially occluded or low-contrast
faces.

### Scoring metrics

**TP / FP / FN — True Positive, False Positive, False Negative**
- **TP**: the detector found a box and it matches a ground-truth box (IoU ≥ 0.5).
- **FP**: the detector found a box but there is no matching ground-truth box — a ghost face.
- **FN**: there is a ground-truth box but the detector found nothing nearby — a missed face.

**Precision**
Of all the boxes the detector reported, what fraction were correct?
`Precision = TP / (TP + FP)`
High precision means few ghost detections.

**Recall**
Of all the real faces in the ground truth, what fraction did the detector find?
`Recall = TP / (TP + FN)`
High recall means few missed faces.

**F1 score**
The harmonic mean of precision and recall.
`F1 = 2 · Precision · Recall / (Precision + Recall)`
A single number that balances both. Used as the primary ranking metric during a sweep
because optimising only precision or only recall produces degenerate solutions
(report nothing → perfect precision; report everything → perfect recall).

---

## Primary backend: OpenCV DNN SSD

Config key | Default | Location
--- | --- | ---
`FACE_DNN_CONFIDENCE_MIN` | `0.3` | `config.py`
`FACE_DNN_NMS_IOU` | `0.4` | `config.py`
`FACE_DNN_FALLBACK_CONFIDENCE_MIN` | `0.15` | `config.py`
`FACE_DNN_FALLBACK_MAX` | `2` | `config.py`

### `FACE_DNN_CONFIDENCE_MIN`

The minimum confidence score a detected box must have to be kept. Applied after
the network forward pass, before NMS.

**Lower value** → more boxes pass the filter.
- More faces found (recall goes up).
- More ghost detections (precision goes down).
- Background textures, clothing, or hands start being reported as faces.

**Higher value** → fewer boxes pass.
- Fewer ghosts (precision goes up).
- Small, blurry, or partially occluded faces are dropped (recall goes down).

Typical sweep range: 0.2 – 0.5.

### `FACE_DNN_NMS_IOU`

The IoU threshold used during Non-Maximum Suppression. Two boxes with IoU above this
value are considered duplicates and the weaker one is discarded.

**Lower value** → NMS is more aggressive.
- Overlapping boxes are suppressed readily.
- In crowds where two faces are close together, one face may be incorrectly suppressed.

**Higher value** → NMS is more permissive.
- Duplicate boxes for the same face survive, increasing FP count.
- Genuine adjacent faces are less likely to suppress each other.

Typical sweep range: 0.3 – 0.6.

### `FACE_DNN_FALLBACK_CONFIDENCE_MIN`

When the primary pass finds zero faces, a second pass over the same DNN output is
performed with this lower threshold. This is a last-resort attempt to find at least
one face on photos where everyone is far away or poorly lit.

Must be strictly lower than `FACE_DNN_CONFIDENCE_MIN` to have any effect.
`FACE_DNN_FALLBACK_MAX` caps how many boxes this pass can contribute.

---

## Fallback backend: OpenCV Haar Cascade

Activated when the DNN finds fewer than `FACE_FALLBACK_MIN_FACE_COUNT` faces.
Provides a complementary detection strategy for the cases where the neural net struggles.

Config key | Default | Location
--- | --- | ---
`FACE_DETECTION_SCALE_FACTOR` | `1.1` | `config.py`
`FACE_DETECTION_MIN_NEIGHBORS` | `8` | `config.py`
`FACE_DETECTION_MIN_SIZE` | `(60, 60)` | `config.py`
`FACE_DETECTION_REQUIRE_EYES` | `1` | `config.py`
`FACE_DETECTION_EYE_MIN_NEIGHBORS` | `3` | `config.py`
`FACE_DETECTION_EYE_MIN_SIZE` | `(15, 15)` | `config.py`

### `FACE_DETECTION_SCALE_FACTOR`

The image is shrunk by this factor at each pyramid level during the cascade scan.
The detector is applied at each scale to find faces of different sizes.

**Closer to 1.0** (e.g. 1.05) → finer scale steps, catches more sizes, slower.
**Larger value** (e.g. 1.3) → coarser scale steps, faster, may miss faces that fall
between scale levels.

### `FACE_DETECTION_MIN_NEIGHBORS`

Each candidate window must be confirmed by at least this many overlapping detections
at neighbouring positions. Acts as a confidence proxy for the Haar detector.

**Lower value** → more faces detected, more false positives (background patterns).
**Higher value** → only strong, repeatedly confirmed detections pass, fewer false positives
but smaller faces or partially visible faces may be missed.

### `FACE_DETECTION_MIN_SIZE`

Minimum bounding box size in pixels. Faces smaller than this are ignored entirely.

**Smaller value** → detects faces further away in the photo; also picks up false positives
from small textures.
**Larger value** → restricts detection to prominent, close-up faces; ignores crowd faces.

### `FACE_DETECTION_REQUIRE_EYES` and eye parameters

After a face region is detected, the cascade optionally verifies that at least one eye
is visible inside it. Reduces false positives caused by non-face oval shapes (helmets,
bib numbers, road markings).

Setting `FACE_DETECTION_REQUIRE_EYES = 0` disables eye verification entirely —
higher recall, more false positives.

---

## Fallback strategy parameters

These control the interaction between the primary DNN backend and the Haar fallback.

Config key | Default | Location
--- | --- | ---
`FACE_FALLBACK_MIN_FACE_COUNT` | `2` | `config.py`
`FACE_FALLBACK_MAX` | `3` | `config.py`
`FACE_FALLBACK_IOU_THRESHOLD` | `0.3` | `config.py`

### `FACE_FALLBACK_MIN_FACE_COUNT`

If the DNN finds fewer faces than this number, the Haar backend is run as a supplement.

Setting this to `1` means Haar only runs when the DNN found zero faces.
Setting it to `3` means Haar runs any time the DNN found 0, 1, or 2 faces —
more aggressive fallback, more chances to recover missed faces, but also more
risk of Haar false positives entering the result.

### `FACE_FALLBACK_IOU_THRESHOLD`

Haar detections that overlap an existing DNN detection by more than this IoU are
discarded as duplicates. Prevents the same face from appearing twice in the output
(once from each backend).

---

## How parameters interact

The parameters are applied in this order during a single photo scan:

```
DNN forward pass
  → filter by FACE_DNN_CONFIDENCE_MIN
  → NMS with FACE_DNN_NMS_IOU
  → if no boxes: second pass at FACE_DNN_FALLBACK_CONFIDENCE_MIN (cap: FACE_DNN_FALLBACK_MAX)
  → if fewer than FACE_FALLBACK_MIN_FACE_COUNT boxes:
      run Haar
      drop Haar boxes with IoU > FACE_FALLBACK_IOU_THRESHOLD vs existing boxes
      cap at FACE_FALLBACK_MAX new boxes
```

A consequence: tuning `FACE_DNN_CONFIDENCE_MIN` downward reduces how often Haar is
invoked, because the DNN now returns more boxes on its own. Conversely, raising it
increases Haar's role.

---

## Scoring and the benchmark

Scoring is implemented in `benchmarking/scoring.py`. The `FaceScorecard` class counts
TP, FP, and FN across all photos in a benchmark split:

```python
class FaceScorecard(BaseModel):
    detection_tp: int
    detection_fp: int
    detection_fn: int
    # computed_field: detection_precision, detection_recall, detection_f1
```

A predicted box counts as a TP only if it overlaps a ground-truth box with IoU ≥ 0.5.
Only ground-truth boxes with `scope="keep"` and `has_coords=True` are counted.
Boxes scoped `exclude` or `uncertain` are invisible to the scorer.

The IoU threshold of 0.5 for scoring is fixed and separate from the NMS threshold —
changing `FACE_DNN_NMS_IOU` does not change the scoring threshold.

---

## Running a parameter sweep

The `bnr benchmark tune` command iterates over a grid of values defined in a YAML file:

```yaml
# benchmarking/tune_configs/face_default.yaml
params:
  FACE_DNN_CONFIDENCE_MIN: [0.2, 0.25, 0.3, 0.35, 0.4]
  FACE_DNN_NMS_IOU: [0.3, 0.4, 0.5]
split: iteration
metric: face_f1
```

With 5 × 3 = 15 combinations the output is a ranked table:

```
Rank  FACE_DNN_CONFIDENCE_MIN  FACE_DNN_NMS_IOU  face_f1  face_P  face_R
   1  0.30                     0.40              78.5%    82.1%   75.2%
   2  0.25                     0.40              77.8%    79.3%   76.4%
Best: FACE_DNN_CONFIDENCE_MIN=0.30, FACE_DNN_NMS_IOU=0.40  (face_f1=78.5%)
```

F1 is the recommended primary metric because it penalises both missing faces and
reporting phantom faces equally.

---

## Quick reference: what to try if scores are low

| Symptom | Likely cause | What to adjust |
|---|---|---|
| Many missed faces (low recall) | Threshold too high | Lower `FACE_DNN_CONFIDENCE_MIN` |
| Many ghost faces (low precision) | Threshold too low | Raise `FACE_DNN_CONFIDENCE_MIN` |
| Duplicate boxes on same face | NMS too permissive | Lower `FACE_DNN_NMS_IOU` |
| Adjacent faces suppressing each other | NMS too aggressive | Raise `FACE_DNN_NMS_IOU` |
| Faces missed in group shots | Haar not triggering | Lower `FACE_FALLBACK_MIN_FACE_COUNT` |
| Haar adding too many ghosts | Haar too sensitive | Raise `FACE_DETECTION_MIN_NEIGHBORS` |
| Small/distant faces missed | Min size too large | Lower `FACE_DETECTION_MIN_SIZE` |
