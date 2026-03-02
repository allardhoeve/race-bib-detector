# Task 084: Unified `album ingest` production pipeline

## Status: DONE

## Goal

Unify the production CLI so that scanning and clustering run in a single `album ingest` command, mirroring how the benchmark runner already does detect → embed → cluster.

## Changes

### New CLI structure
- `bnr album ingest <path>` — full pipeline: scan all photos + cluster faces
- `bnr album rescan <hash-or-index>` — rescan one photo + re-cluster its album
- `bnr album list` / `bnr album forget` — unchanged

### New service functions (`scan/service.py`)
- `ingest_album(source, limit, album_label, album_id)` — validates input, scans directory, clusters faces
- `rescan_and_cluster(identifier)` — looks up photo, rescans, re-clusters album
- `_resolve_album_id()` — extracted helper for album ID resolution

### Deleted
- `cli/scan.py` — old `bnr scan` command
- `cli/faces.py` — old `bnr faces cluster` command
- `scan.service.run_scan()` — replaced by `ingest_album()`
- `scan.service.resolve_face_mode()` — face mode flags removed (always run both detectors)
- `tests/test_scan_service.py` — tested deleted code

### Tests
- `tests/test_cli_album.py` — 14 tests (parsing for ingest/rescan subcommands)
- `tests/test_album_ingest.py` — 12 tests (service-layer orchestration)
- Full suite: 614 passed, 8 skipped
