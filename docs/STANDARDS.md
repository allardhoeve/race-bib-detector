# Coding Standards

This document captures shared, stable conventions so they do not get repeated across plans and notes.

## Photo Identification
- Use the 8-character photo hash as the primary identifier in code, UI, logs, URLs, and discussions.
- Do not use database IDs to identify photos outside storage internals.
- The canonical photo hash is computed in `photo.py` via `compute_photo_hash()` and is derived from the photo URL using SHA-256, first 8 characters.

## Hashing Conventions
- Photo identity hash: SHA-256, 8 characters (photo URL -> `compute_photo_hash()`).
- Cache file naming hash: MD5, 12 characters (used only for cache filenames).
- Do not mix these two hashes. Photo identity always uses the photo hash, and cache file paths always use the cache hash.

## Python Environment
- Always use the virtual environment executables.
- Use `venv/bin/python` and `venv/bin/pip`.
- Do not use `python`, `python3`, `pip`, or `pip3`.

## Entrypoints
- Any new runnable script must start with `#!/usr/bin/env python`.
- Entry points must be `chmod 755`.
- If you add a new entrypoint, include it in `tests/test_entrypoints.py` so the smoke test covers it.

## Configuration
- All tunable detection parameters live in `config.py`.
- Do not hardcode thresholds or pipeline constants outside `config.py`.

## Idempotency
- Web and CLI tools should be safe to run multiple times without corrupting or duplicating state.
- Assume scans may be re-run, and partial data may already exist.
- Example: when tagging photos for a reference set, preserve existing tags, allow edits, and initialize missing entries with defaults.

## Data Locality
- Sensitive data (e.g., face embeddings and related metadata) must remain local.
- Do not call external/cloud services for face data or storage.

## Logging And Traceability
- All automated detections and links must be traceable.
- Store evidence for derived results (inputs, confidences, model/version, and provenance).
- Prefer structured logging with enough context to reproduce outcomes.

## Logging
If you write logging, see LOGGING.md.

## Data Retention And Deletion
- Do not create hidden copies of sensitive data.
- Any derived data must be deletable by photo hash and by album.
- Retain only what is needed for repeatability and UI traceability.

## UI Separation
- Keep inspection/debug UIs separate from customer-facing UI.
- Customer UI should not expose face clusters or internal debug metadata.

## Logging
- Use `logging.getLogger(__name__)` in modules; do not use `print()` for runtime output.
- Configure logging once in entrypoints using `logging_utils.configure_logging()`.
- Default logging level is `INFO`. Use `DEBUG` for detailed per-item output, `WARNING` for recoverable issues, and `ERROR`/`CRITICAL` for failures.
- When handling exceptions, use `logger.exception(...)` to capture stack traces.
- CLI endpoints must expose:
  - `--log-level` (`debug`, `info`, `warning`, `error`, `critical`) to set an explicit level.
  - `-v/--verbose` and `-q/--quiet` to adjust level relative to `INFO` (more `-v` = more detail, more `-q` = less detail).
  - `--log-level` overrides `-v/--quiet` when provided.
