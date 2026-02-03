# TODO - Comparison Mode

Goal: Compare two runs or configurations and report deltas.

## Decisions

- **Regression focus**: Highlight regressions on the full set to catch changes that hurt overall performance.
- **Depends on**: todo_reporting.md (need stored results from multiple runs).
- **Baseline workflow**: If metrics improve on `full` split, offer to update baseline automatically.

## Tasks

- [x] Add ability to compare current run against baseline.
- [x] Report deltas in TP/FP/FN and summary metrics.
- [x] Highlight regressions (photos that got worse) on the full set.
- [x] Implement automatic baseline update offer when metrics improve.

## Implementation

Comparison is integrated into `benchmarking/cli.py`:
- `benchmark -s full` compares against baseline and shows deltas
- `update-baseline` runs benchmark and offers to update if improved

Output shows:
- Baseline commit and timestamp
- Precision/recall/F1 deltas with direction
- Final judgement: IMPROVED / REGRESSED / NO CHANGE
- Exit code 1 on regression (for CI/agent integration)
