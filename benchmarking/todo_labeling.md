# TODO - Labeling and Sample Set

Goal: Create a repeatable way to build and maintain the ground-truth sample set from a fixed photo directory, with duplicate detection and editing.

Tasks:
- [ ] Define a stable image hashing approach for duplicate detection (file hash vs perceptual hash).
- [ ] Use content hash as canonical identity; store optional photo hash for integration.
- [ ] Define the fixed source photo directory (global path).
- [ ] Add a scanning step that:
  - iterates photos in the fixed directory
  - computes hashes
  - maps each hash to a canonical ground-truth key
  - detects duplicates and links them to a single entry
- [ ] Define edit behavior when a duplicate is found (open existing labels vs create new).
- [ ] Store or update entries in `benchmarking/ground_truth.json` without deleting existing labels.
- [ ] Track file-to-hash mapping so reruns are stable and incremental (e.g., mapping file).

Deliverable:
- A documented flow (CLI or UI) that can build and update the sample set without losing prior labels.
