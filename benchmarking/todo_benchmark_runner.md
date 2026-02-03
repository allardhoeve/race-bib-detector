# TODO - Benchmark Runner

Goal: Implement a runner that evaluates detection accuracy against ground truth.

## Decisions

- **Batch operation**: Run detection on all photos in the selected split or full set as a batch job.
- **Depends on**: todo_labeling.md (ground truth must exist).

## Tasks

- [ ] Load `benchmarking/ground_truth.json` and validate schema.
- [ ] Run detection for each photo in the selected split or full set.
- [ ] Compare detected vs expected bibs per photo.
- [ ] Compute per-photo TP/FP/FN and aggregate metrics (precision, recall, F1).
- [ ] Store results for later comparison and reporting.

## Deliverable

- A CLI that runs detection against ground truth and outputs metrics.
