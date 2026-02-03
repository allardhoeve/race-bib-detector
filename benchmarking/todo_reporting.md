# TODO - Reporting

Goal: Provide clear, comparable benchmark outputs.

## Decisions

- **Per-photo status**: Use PASS/PARTIAL/MISS to indicate correctness at a glance.
  - PASS = all expected bibs found, no false positives
  - PARTIAL = some but not all expected bibs found
  - MISS = none of the expected bibs found
- **Depends on**: todo_benchmark_runner.md (results must exist).

## Tasks

- [ ] Implement detailed metrics table output (Option B from BENCHMARKING.md) as default.
- [ ] Add tag-based slicing (e.g., metrics for dark_bib only).
- [ ] Include per-photo status (PASS, PARTIAL, MISS).

## Deliverable

- Formatted benchmark reports that show both aggregate metrics and per-photo details.
