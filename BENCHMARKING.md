# Benchmarking System Design

## Problem Statement

When tuning detection parameters or adding preprocessing steps (like CLAHE), we risk:
1. **Regression** - Fixing one photo breaks detection on others
2. **False improvements** - A change helps one edge case but hurts the common case
3. **Unmeasured tradeoffs** - Better recall but worse precision (or vice versa)

We need an objective way to measure detection quality across a representative set of photos.

## Key Questions to Resolve

### 1. Ground Truth: How do we define "correct" detections?

**Option A: Manual labeling**
- Create a JSON file with expected bib numbers per photo
- Pros: Definitive truth, catches both false positives and false negatives
- Cons: Labor-intensive, need to maintain as test set grows

**Option B: Use current detections as baseline**
- Run current pipeline, save results as "expected"
- Pros: Quick to set up, automatically covers current behavior
- Cons: Codifies current bugs as "correct", doesn't catch false negatives

**Option C: Hybrid approach**
- Start with current detections as baseline
- Manually verify and correct a subset of "golden" photos
- Track regressions against baseline, improvements against golden set

**Recommendation:** Option C - Start with baseline, gradually build golden set for edge cases.

### 2. Test Set: Which photos to include?

**Categories to cover:**
- ✅ Clear, well-lit bibs (the common case)
- ✅ Dark/shadowy bibs (like ae7dc104)
- ✅ Gray/off-white bibs (like b54bd347)
- ✅ Multiple bibs in one photo
- ✅ Small bibs (relative to image)
- ✅ No bibs (to test false positive rate)
- ✅ Partial/obscured bibs

**Size considerations:**
- Too small: Not representative
- Too large: Slow to run, hard to maintain
- **Suggestion:** 20-50 photos covering all categories

### 3. Metrics: What do we measure?

**Per-photo metrics:**
- True Positives (TP): Correctly detected bibs
- False Positives (FP): Detected bibs that don't exist
- False Negatives (FN): Missed bibs that should be detected

**Aggregate metrics:**
- **Precision** = TP / (TP + FP) - "Of detections made, how many are correct?"
- **Recall** = TP / (TP + FN) - "Of bibs that exist, how many did we find?"
- **F1 Score** = 2 * (Precision * Recall) / (Precision + Recall) - Balanced measure

**Additional useful metrics:**
- Detection count per photo (to spot over/under-detection)
- Confidence distribution (are we making low-confidence guesses?)
- Processing time (to catch performance regressions)

### 4. Output Format: How do we present results?

**Option A: Simple pass/fail**
```
Running benchmark...
Photo ae7dc104: FAIL (expected [600], got [])
Photo b54bd347: PASS
...
Total: 45/50 passed (90%)
```

**Option B: Detailed metrics table**
```
| Photo    | Expected | Detected | TP | FP | FN | Status |
|----------|----------|----------|----|----|----| -------|
| ae7dc104 | 600      | -        | 0  | 0  | 1  | MISS   |
| b54bd347 | 405,411  | 21,405   | 1  | 1  | 1  | PARTIAL|
...
Precision: 85.2%  Recall: 78.4%  F1: 81.6%
```

**Option C: Comparison mode (for A/B testing)**
```
Comparing: baseline vs clahe_pipeline

| Photo    | Baseline      | CLAHE         | Change |
|----------|---------------|---------------|--------|
| ae7dc104 | [] (miss)     | [600] (hit)   | +1 TP  |
| b54bd347 | [21,405]      | [405,411]     | -1 FP, +1 TP |
...
Net change: +5 TP, -2 FP, +3 recall
```

**Recommendation:** Option C with Option B as default view.

### 5. Integration: How do we run benchmarks?

**As a CLI tool:**
```bash
# Run benchmark with current pipeline
venv/bin/python benchmark.py

# Run with specific config
venv/bin/python benchmark.py --clahe --threshold=180

# Compare two configurations
venv/bin/python benchmark.py --compare baseline clahe
```

**As part of CI (optional):**
- Run on PR to catch regressions
- Block merge if precision/recall drops below threshold

---

## Proposed Design

### File Structure

```
benchmark/
├── __init__.py
├── runner.py          # Main benchmark execution
├── metrics.py         # Precision/recall calculations
├── comparison.py      # A/B comparison logic
└── report.py          # Output formatting

benchmark_data/
├── ground_truth.json  # Expected detections per photo
├── test_images/       # Symlinks or copies of test photos
└── results/           # Saved benchmark runs
    ├── baseline_2024-01-15.json
    └── clahe_test_2024-01-16.json
```

### Ground Truth Format

```json
{
  "version": 1,
  "photos": {
    "ae7dc104": {
      "expected_bibs": ["600"],
      "category": "dark",
      "notes": "Very dark image, bib only visible with contrast enhancement"
    },
    "b54bd347": {
      "expected_bibs": ["21", "405", "411"],
      "category": "gray_bibs",
      "notes": "Gray bibs in overcast lighting"
    },
    "abc12345": {
      "expected_bibs": [],
      "category": "no_bibs",
      "notes": "Crowd shot, no visible bib numbers"
    }
  }
}
```

### Benchmark Result Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "config": {
    "pipeline": "grayscale+resize",
    "target_width": 1280,
    "white_threshold": 200,
    "clahe_enabled": false
  },
  "summary": {
    "total_photos": 50,
    "precision": 0.852,
    "recall": 0.784,
    "f1": 0.816,
    "processing_time_seconds": 125.3
  },
  "per_photo": {
    "ae7dc104": {
      "expected": ["600"],
      "detected": [],
      "tp": 0, "fp": 0, "fn": 1,
      "status": "miss"
    }
  }
}
```

---

## Questions for You

1. **Ground truth source:** Should we start by manually labeling ~20 photos, or bootstrap from current detections?

2. **Test set location:** Use photos already in cache, or create a dedicated `benchmark_data/test_images/` folder?

3. **Categories:** Are the categories I listed sufficient? Any edge cases I'm missing?

4. **Comparison baseline:** What should "baseline" be - the current pipeline before any changes, or a specific saved configuration?

5. **CI integration:** Is this worth integrating into CI, or is manual benchmark runs sufficient for now?

6. **Tolerance:** Should exact match be required, or is partial detection acceptable (e.g., detecting 2 of 3 bibs in a photo)?
