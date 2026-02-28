# Task 042: Empirical bib-face spatial analysis

Independent analysis task. No dependencies.

## Goal

Measure actual spatial relationships between linked bib and face boxes in the ground truth data, derive empirically-grounded multipliers, and make the torso region heuristic configurable.

## Background

`_torso_region()` used guessed multipliers: torso starts at face bottom edge, extends 2× face-height downward, ±1 face-width horizontally. With 281 GT-linked pairs we measured the actual distribution and found the old heuristic only covered 75.4% of links.

## Findings

All offsets measured from face center, normalised by face height.

| Metric | Median | p5 | p95 | Min | Max |
|---|---|---|---|---|---|
| Vertical | +2.24 | +1.45 | +2.77 | +1.03 | +3.41 |
| Horizontal | +0.07 | −0.14 | +0.33 | −0.49 | +0.58 |

Horizontal asymmetry (+0.07 median) is a camera-position artefact (photographer on outside corner of turn). Flips for track events (counter-clockwise). Torso region stays symmetric.

## Changes

### `benchmarking/link_analysis.py` (new)

Standalone analysis script. Loads all three GT files, computes per-pair offsets, prints summary statistics and coverage. Run: `venv/bin/python -m benchmarking.link_analysis`

### `config.py`

New config keys with margin beyond p5/p95 envelope:

| Key | Value | Unit | Rationale |
|---|---|---|---|
| `AUTOLINK_TORSO_TOP` | `1.0` | face-heights | Below p5 (1.45), catches close-ups |
| `AUTOLINK_TORSO_BOTTOM` | `3.5` | face-heights | Above max (3.41), catches distant shots |
| `AUTOLINK_TORSO_HALF_WIDTH` | `0.6` | face-heights | Above max abs (0.58), symmetric |

### `faces/autolink.py`

`_torso_region()` now reads from config instead of hardcoded values. Offsets are from face center in face-height units (was: from face bottom edge in face-width units for horizontal).

### `docs/TUNING.md`

New "Bib-face autolink" section documenting empirical findings and config keys.

## Verification

```
venv/bin/python -m benchmarking.link_analysis    # coverage should be 100%
venv/bin/python -m pytest tests/ -x -q           # 403 passed
```
