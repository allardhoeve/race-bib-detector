# TODO - Reporting

Goal: Provide clear, comparable benchmark outputs.

## Decisions

- **Per-photo status**: Use PASS/PARTIAL/MISS to indicate correctness at a glance.
  - PASS = all expected bibs found, no false positives
  - PARTIAL = some but not all expected bibs found (or has false positives)
  - MISS = none of the expected bibs found
- **Depends on**: todo_benchmark_runner.md (results must exist).
- **Detailed output**: Show metrics that help interpret results and guide improvements.

## Tasks

- [x] Implement detailed metrics table output (Option B from BENCHMARKING.md) as default.
- [x] Add tag-based slicing (e.g., metrics for dark_bib only, obscured_bib only).
- [x] Include per-photo status (PASS, PARTIAL, MISS).
- [x] Show aggregate metrics: precision, recall, F1.
- [x] Show summary judgement: IMPROVED / REGRESSED / NO CHANGE.

## Implementation

Reporting is integrated into `benchmarking/cli.py` `benchmark` command.

Output includes:
- Split and photo count
- Runtime
- Precision, recall, F1 metrics
- TP/FP/FN totals
- Photo status breakdown (PASS/PARTIAL/MISS counts)
- Tag-based breakdown (if tags present)
- Baseline comparison (for full split)
- Final judgement with exit code
