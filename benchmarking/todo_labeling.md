# TODO - Labeling and Sample Set

Goal: Create a repeatable way to build and maintain the ground-truth sample set from a fixed photo directory, with duplicate detection and editing.

## Decisions

- **Hashing**: Use SHA256 of file bytes for content hashing (simple, deterministic, duplicates not a significant concern).
- **Source directory**: `photos/` is the fixed source directory for benchmark photos.
- **Duplicate handling**: When a duplicate is found, open existing labels for editing rather than creating a new entry.

## Tasks

- [x] Implement SHA256-based content hashing for photos.
- [x] Use content hash as canonical identity; store optional photo hash for integration with existing code.
- [x] Add a scanning step that:
  - iterates photos in `photos/`
  - computes SHA256 hashes
  - maps each hash to a canonical ground-truth key
  - detects duplicates and links them to a single entry
- [x] Store or update entries in `benchmarking/ground_truth.json` without deleting existing labels.
- [x] Track file-to-hash mapping so reruns are stable and incremental (e.g., `benchmarking/photo_index.json`).

## Deliverable

- [x] A scanner (CLI) that can build and update the sample set incrementally without losing prior labels.
- This is a prerequisite for the labeling UI.

## Implementation

- `benchmarking/scanner.py` - Photo scanning and SHA256 hashing
- `benchmarking/ground_truth.py` - Ground truth data structures and I/O
- `benchmarking/photo_index.py` - File-to-hash mapping
- `benchmarking/cli.py` - CLI commands: `scan`, `stats`, `unlabeled`, `show`, `label`

Usage:
```bash
python -m benchmarking.cli scan        # Scan photos/ and update index
python -m benchmarking.cli stats       # Show labeling statistics
python -m benchmarking.cli unlabeled   # List unlabeled photos
python -m benchmarking.cli show HASH   # Show details for a photo
python -m benchmarking.cli label HASH -b "123,456" -t "dark_bib"  # Label via CLI
```
