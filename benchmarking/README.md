# Benchmarking Data Layout

This directory contains benchmark data and documentation for the bib detection evaluation.

## Implementation Order

1. **todo_labeling.md** - Scanning, hashing, ground_truth.json structure
2. **todo_ui.md** - Fast labeling interface
3. **todo_benchmark_runner.md** - Run detection in batch, compare to ground truth
4. **todo_reporting.md** - Output formatting
5. **todo_comparison.md** - Diff two runs

## Files

Planned files:
- `benchmarking/ground_truth.json` - Manual labels (bibs, tags, split) per photo
- `benchmarking/photo_index.json` - Maps content hashes to file paths
- `benchmarking/results/` - Stored benchmark run outputs
- `benchmarking/BENCHMARKING.md` - Design document

## Ground Truth Schema

Top-level fields:
- `version`: integer schema version
- `tags`: list of allowed tag values
- `photos`: map keyed by content hash (SHA256)

Each photo entry fields:
- `bibs`: list of integer bib numbers, no duplicates
- `tags`: list of zero or more tag strings from the allowed set
- `split`: fixed split label for the photo
- `content_hash`: required canonical identity (SHA256 of file bytes)
- `photo_hash`: optional 8-character hash used by existing URL/path-based code

Allowed tag values (initial list):
- dark_bib
- no_bib (mnemonic for photos intentionally without bibs, for false-positive testing)
- blurry_bib
- light_bib
- light_faces
- other_banners

Split labels:
- `iteration`
- `full`

Example:
```json
{
  "version": 1,
  "tags": [
    "dark_bib",
    "no_bib",
    "blurry_bib",
    "light_bib",
    "light_faces",
    "other_banners"
  ],
  "photos": {
    "8c1a2f4b5d7e9a01...": {
      "content_hash": "8c1a2f4b5d7e9a01...",
      "photo_hash": "ae7dc104",
      "bibs": [600],
      "tags": ["dark_bib"],
      "split": "iteration"
    }
  }
}
```

## Usage Notes

- The ground truth is manual and authoritative.
- The split is fixed per photo to keep comparisons stable across runs.
- Benchmark outputs should support both split-only and full-set reporting.
- Advanced labeling with bib locations can be added later as optional fields.

## Photo Index Mapping

`benchmarking/photo_index.json` maps content hashes to one or more file paths.
This preserves information about duplicates while keeping labels single-entry.
