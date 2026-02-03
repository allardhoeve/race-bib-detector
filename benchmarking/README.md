# Benchmarking Data Layout

This directory contains benchmark data and documentation for the bib detection evaluation.

## Files

Planned files:
- `benchmarking/ground_truth.json`
- `benchmarking/results/`
- `benchmarking/BENCHMARKING.md`

## Ground Truth Schema

Top-level fields:
- `version`: integer schema version
- `tags`: list of allowed tag values
- `photos`: map keyed by 8-character photo hash

Each photo entry fields:
- `bibs`: list of integer bib numbers, no duplicates
- `tags`: list of zero or more tag strings from the allowed set
- `split`: fixed split label for the photo

Allowed tag values (initial list):
- dark_bib
- no_bib
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
    "ae7dc104": {
      "bibs": [600],
      "tags": ["dark_bib"],
      "split": "iteration"
    },
    "b54bd347": {
      "bibs": [21, 405, 411],
      "tags": ["light_bib"],
      "split": "full"
    }
  }
}
```

## Usage Notes

- The ground truth is manual and authoritative.
- The split is fixed per photo to keep comparisons stable across runs.
- Benchmark outputs should support both split-only and full-set reporting.
- Advanced labeling with bib locations can be added later as optional fields.
