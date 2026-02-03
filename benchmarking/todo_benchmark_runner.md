# TODO - Benchmark Runner

Goal: Implement a runner that evaluates detection accuracy against ground truth.

Tasks:
- [ ] Load `benchmarking/ground_truth.json` and validate schema.
- [ ] Run detection for each photo in the selected split or full set.
- [ ] Compare detected vs expected bibs per photo.
- [ ] Compute per-photo TP/FP/FN and aggregate metrics.
