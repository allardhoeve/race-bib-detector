# TODO - Comparison Mode

Goal: Compare two runs or configurations and report deltas.

## Decisions

- **Regression focus**: Highlight regressions on the full set to catch changes that hurt overall performance.
- **Depends on**: todo_reporting.md (need stored results from multiple runs).

## Tasks

- [ ] Add ability to compare two runs/configs by name or timestamp.
- [ ] Report deltas in TP/FP/FN and summary metrics.
- [ ] Highlight regressions (photos that got worse) on the full set.

## Deliverable

- A comparison report showing what changed between two benchmark runs.
