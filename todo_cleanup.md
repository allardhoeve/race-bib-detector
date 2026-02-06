# TODO: Cache Cleanup + Album Forget Files

## Goals
- [ ] Ensure `bnr album forget` removes cached artifacts under `cache/` for the album without touching originals in `photos/` (or any other source directory).
- [ ] Provide a standalone cleanup command for disk hygiene when cache grows large.
- [ ] Make cleanup idempotent and safe (dry-run by default).

## Decisions Needed
- [x] Define what counts as “album-owned” cache (e.g., only cache files referenced by `photos.cache_path` for the album, plus derived artifacts named from the cache filename).
- [x] Delete face evidence JSON (`cache/faces/evidence/*.json`) during album forget.
- [x] Never delete files in `photos/` (or any originals/source directories).
- [ ] Decide whether to keep a tombstone or log of deleted paths for auditability.

## Plan
- [ ] Add a cache cleanup module (e.g., `cache/cleanup.py` or `cli/cache.py`) that can:
- [ ] Build a set of “owned” cache filenames from DB `photos.cache_path` values.
- [ ] Derive all related artifact paths for each cache filename:
- [ ] `cache/<hash>.jpg`
- [ ] `cache/gray_bounding/<hash>.jpg`
- [ ] `cache/candidates/<hash>.jpg`
- [ ] `cache/snippets/<hash>_bib*.jpg`
- [ ] `cache/faces/snippets/<hash>_face*.jpg`
- [ ] `cache/faces/boxed/<hash>_face*_boxed.jpg`
- [ ] `cache/faces/evidence/<photo_hash>_faces.json`
- [ ] For album forget: gather photo hashes and cache filenames for that album; remove only those derived paths.
- [ ] For global cleanup: optionally remove unreferenced cache/derived files not present in DB.
- [ ] Implement `--dry-run`/`-n` that reports counts and paths without deleting.
- [ ] Default to deletion (no flag) for cleanup command, with clear logging and error handling.
- [ ] Wire into `bnr album forget` to call cleanup before DB deletion (needs DB info to resolve cache paths).
- [ ] Update docs (`STRUCTURE.md` or `TODO.md`) to mention cleanup behavior and safety notes.
- [ ] Add tests for:
- [ ] Album forget removes only cache artifacts and not source originals.
- [ ] Cleanup ignores missing files and is idempotent.
- [ ] Cleanup does not cross outside `cache/`.

## Safety Notes
- [ ] Never delete files outside `cache/`.
- [ ] Require explicit `--apply` for destructive cleanup.
- [ ] Log counts and sample paths before deletion.
