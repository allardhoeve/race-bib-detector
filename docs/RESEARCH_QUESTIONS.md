# Research Questions

Open questions about detection quality, ordered by expected impact.
Each can be answered by running benchmark comparisons.

---

## Bib detection

### Does the full-image OCR fallback help?

The bib pipeline runs OCR twice: first on white-region candidates, then on the
full image as a fallback (`detection/detector.py:155`). The fallback uses a
higher confidence threshold (0.5 vs 0.4) but still adds processing time.

**Experiment:** Run the benchmark with and without the full-image pass. Compare
`BibScorecard` recall. If the delta is negligible, remove the pass.

### Are the white-region thresholds optimal?

White region selection (`config.py:34–61`) uses fixed thresholds:
`WHITE_THRESHOLD=200`, `MEDIAN_BRIGHTNESS_THRESHOLD=120`,
`MEAN_BRIGHTNESS_THRESHOLD=100`, `MIN_CONTOUR_AREA=1000`.

These were hand-tuned for race photos with white bibs. They may reject valid
bibs on coloured backgrounds or in shadow. None of these are currently exposed
in `PipelineConfig` or sweepable via the tuner.

**Experiment:** Expose key thresholds in `PipelineConfig`, extend the tuner to
sweep bib detection parameters, and measure precision/recall across the grid.

### Does OCR confidence threshold tuning improve bib accuracy?

`WHITE_REGION_CONFIDENCE_THRESHOLD=0.4` and `FULL_IMAGE_CONFIDENCE_THRESHOLD=0.5`
(`config.py:68–71`) gate which EasyOCR detections are kept. Lower values recover
more bibs but risk false positives (clothing text, sponsor logos).

**Experiment:** Sweep both thresholds and measure the precision/recall curve.

### Is substring deduplication correctly calibrated?

When "600" and "6600" overlap, the shorter is kept only if its confidence is
1.5× higher (`SUBSTRING_CONFIDENCE_RATIO`, `config.py:89`). This heuristic may
over- or under-filter.

**Experiment:** Collect cases from the benchmark where substring filtering fires
and check whether the right detection survives.

---

## Preprocessing

### Does conditional CLAHE outperform always-on?

CLAHE is only applied when the image dynamic range (p95−p5) is below
`CLAHE_DYNAMIC_RANGE_THRESHOLD=60` (`config.py:26`). This avoids boosting
noise on already-contrasty images, but may skip photos that would benefit.

**Experiment:** Compare three modes — always-on, conditional (current), and off —
on bib and face scorecards.

### What CLAHE parameters are optimal?

`clahe_clip_limit=2.0` and `clahe_tile_size=(8,8)` are already in
`PipelineConfig` but haven't been systematically swept for bib detection.

**Experiment:** Grid sweep `clip_limit × tile_size` and measure bib F1.

### Does target width affect detection quality?

Images are resized to `TARGET_WIDTH=1280` before OCR (`config.py:14`).
Larger might improve OCR on small bibs; smaller might reduce noise.

**Experiment:** Sweep `target_width` in [640, 1280, 1920] and measure bib
scorecard precision/recall.

---

## Face detection

### When does the Haar fallback actually help?

The Haar cascade runs when the DNN finds fewer than
`FACE_FALLBACK_MIN_FACE_COUNT=2` faces. On photos where the DNN performs well,
Haar adds nothing. On photos where it struggles, Haar may add ghosts.

**Experiment:** Run the benchmark with fallback disabled (`FACE_FALLBACK_BACKEND=None`)
and compare `FaceScorecard` recall/precision to the current configuration.

### Is the DNN fallback confidence band useful?

When no faces pass `FACE_DNN_CONFIDENCE_MIN=0.3`, a second pass at
`FACE_DNN_FALLBACK_CONFIDENCE_MIN=0.15` tries to recover something. This
confidence band [0.15, 0.3) may contain mostly noise or mostly real faces.

**Experiment:** Log how often the fallback fires and what fraction of its
detections are TPs. If low, raise or remove the band.

See also: [TUNING.md](TUNING.md) for a full explanation of face detection
parameters and how to run a parameter sweep.

---

## Linking

### Are the torso-region heuristics empirically valid?

`faces/autolink.py` estimates a torso region as 2× face-height below the face,
±1 face-width horizontally. These ratios are hardcoded guesses.

**Experiment:** On the ground-truth linked photos, measure where bib centroids
actually fall relative to face boxes. Derive empirical multipliers.

### Should linking use assignment optimisation?

The current linker uses greedy nearest-match. In crowded photos with multiple
faces and bibs, the Hungarian algorithm (optimal assignment) might produce
better pairings.

**Experiment:** Implement an alternative linker using `scipy.optimize.linear_sum_assignment`
and compare `LinkScorecard` on the benchmark set.

---

## Parameter interaction

### How do parameters interact across the pipeline?

Most parameters have been tuned in isolation. Changing preprocessing (e.g. CLAHE
clip limit) shifts the optimal detection thresholds. A joint sweep would reveal
these interactions but is combinatorially expensive.

**Approach:** Start with the highest-leverage single-parameter sweeps above.
If two parameters show strong individual effects, do a focused 2D sweep on
that pair. Avoid full grid search until single-factor effects are understood.

---

## Infrastructure gaps

The tuner (`benchmarking/tuner.py`) currently supports face detection sweeps
only. To answer the bib and preprocessing questions above, it needs to be
extended to accept bib pipeline parameters. This is a prerequisite for most
experiments in the "Bib detection" and "Preprocessing" sections.
