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

## Bib-face autolink (torso region)

The autolink predictor (`faces/autolink.py`) uses a spatial heuristic to link detected
bibs to detected faces. It estimates a "torso region" below each face and checks which
bib centroids fall inside it.

### Empirical findings (task-042, N=281 linked pairs)

All offsets are measured from the **face center**, normalised by **face height** (for
aspect-ratio independence).

| Metric | Median | p5 | p95 | Min | Max |
|---|---|---|---|---|---|
| Vertical (bib below face) | +2.24 | +1.45 | +2.77 | +1.03 | +3.41 |
| Horizontal (bib right of face) | +0.07 | −0.14 | +0.33 | −0.49 | +0.58 |

**Horizontal asymmetry**: the slight rightward bias (+0.07 median) is an artefact of
photographer position — typically on the outside corner of a road turn. For track events
(counter-clockwise running) the bias would flip. The torso region should therefore remain
symmetric; the per-event skew is not a stable prior.

**Coverage of current heuristic**: 75.4% of GT links fall inside the old hardcoded
`_torso_region()` (starts at face bottom edge, 2× face-height downward, ±1 face-width
horizontal). Misses are mostly bibs that are further below the face than 2.5 fh.

### Running the distance analyser

```
venv/bin/python -m benchmarking.link_analysis
```

The script loads the three ground truth files (`bib_ground_truth.json`,
`face_ground_truth.json`, `bib_face_links.json`), finds every linked (bib, face) pair
with valid coordinates, and prints:

1. **Offset statistics** — per-pair vertical and horizontal displacement of the bib
   centroid from the face centroid, normalised by face height. Also Euclidean distance
   and angle. For each metric: median, mean, stdev, p5/p95, min/max.
2. **Coverage** — what percentage of GT links fall inside the current `_torso_region()`
   heuristic (as configured in `config.py`). This is the key number: if it drops below
   100%, some real links are outside the search region and will be missed by autolink.
3. **Suggested multipliers** — the p5/p95 envelope, which represents the tightest
   region that still captures 90% of GT links.

**How to interpret the output:**

- **Coverage < 100%** means the torso region is too tight. Widen `AUTOLINK_TORSO_TOP`
  (lower value = higher on the body), `AUTOLINK_TORSO_BOTTOM` (higher value = further
  down), or `AUTOLINK_TORSO_HALF_WIDTH` (wider horizontal search).
- **Coverage = 100% but autolink has false positives** means the region is too generous.
  Tighten the values toward the p5/p95 envelope printed in "Suggested multipliers".
- **Horizontal median far from zero** is expected — it reflects camera angle, which
  varies per event. The region should stay symmetric because the bias flips depending
  on which side of the course the photographer stands.

Re-run the analyser after adding more GT links or changing config values to verify
the effect.

### Config keys

Config key | Default | Unit | Meaning
--- | --- | --- | ---
`AUTOLINK_TORSO_TOP` | `1.0` | face-heights | Top of torso region below face center
`AUTOLINK_TORSO_BOTTOM` | `3.5` | face-heights | Bottom of torso region below face center
`AUTOLINK_TORSO_HALF_WIDTH` | `0.6` | face-heights | Half-width of torso region from face center

Defaults are set with margin beyond the p5/p95 envelope to avoid clipping edge cases.
The region is symmetric horizontally because camera angle varies per event.

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
