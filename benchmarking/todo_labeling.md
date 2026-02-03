# TODO - Labeling and Sample Set

Goal: Create a repeatable way to build and maintain the ground-truth sample set from a fixed photo directory, with duplicate detection and editing.

## Decisions

- **Hashing**: Use SHA256 of file bytes for content hashing (simple, deterministic, duplicates not a significant concern).
- **Source directory**: `photos/` is the fixed source directory for benchmark photos.
- **Duplicate handling**: When a duplicate is found, open existing labels for editing rather than creating a new entry.

## Tasks

- [ ] Implement SHA256-based content hashing for photos.
- [ ] Use content hash as canonical identity; store optional photo hash for integration with existing code.
- [ ] Add a scanning step that:
  - iterates photos in `photos/`
  - computes SHA256 hashes
  - maps each hash to a canonical ground-truth key
  - detects duplicates and links them to a single entry
- [ ] Store or update entries in `benchmarking/ground_truth.json` without deleting existing labels.
- [ ] Track file-to-hash mapping so reruns are stable and incremental (e.g., `benchmarking/photo_index.json`).

## Deliverable

- A scanner (CLI) that can build and update the sample set incrementally without losing prior labels.
- This is a prerequisite for the labeling UI.
