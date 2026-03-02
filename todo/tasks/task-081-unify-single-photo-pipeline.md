# Task 081: Unify single-photo pipeline between production and benchmarking

Should be done **before** the tuning epic (071–077) so tuning improvements apply to both paths automatically.

## Goal

Extract one `run_single_photo()` function that both production scan and benchmark runner call. Today the same detection logic is implemented twice — `scan/pipeline.py:process_image()` and `benchmarking/runner.py:_run_bib_detection()` + `_run_face_detection()` — and they've diverged. Production has the face fallback chain but no normalization or linking. Benchmarking has normalization and linking but no fallback chain. Neither calls the other.

## Background

The system's purpose is photo retrieval: find photos by bib number or face. The single-photo pipeline is:

```
decode image (once)
    ├── detect bibs → normalize to [0,1]
    ├── detect faces (with fallback) → normalize to [0,1] → embed
    └── link bibs ↔ faces
```

This pipeline should be **identical** for production and benchmarking. The only difference is what happens with the result:

- **Production**: persist bibs, faces, embeddings, and links to SQLite for retrieval
- **Benchmarking**: score against ground truth, collect diagnostics, write JSON

Today these are two separate code paths that duplicate image decoding, bib detection, and face detection with subtle differences.

### Current divergence

| Step | Production (`scan/pipeline.py`) | Benchmarking (`runner.py`) |
|------|------|------|
| Decode image | `cv2.imdecode` (line 193) | `cv2.imdecode` (line 479) |
| Detect bibs | `detect_bib_numbers()` (line 179) | `detect_fn()` (line 419) |
| Normalize bibs to [0,1] | missing | `BibBox(x=x1/img_w, ...)` (line 438) |
| Detect faces | `face_backend.detect_face_candidates()` (line 198) | `face_backend.detect_face_candidates()` (line 485) |
| Face fallback chain | 40 lines of fallback logic (lines 201–254) | missing |
| Normalize faces to [0,1] | missing | `FaceBox(x=x1/face_w, ...)` (line 492) |
| Embed faces | `embedder.embed()` (line 260) | separate in `_assign_face_clusters` |
| Link bibs ↔ faces | missing | `predict_links()` (line 646) |
| Store results | SQLite via `db.insert_*` | `PhotoResult` dataclass → JSON |

## Design decisions

| Question | Decision |
|----------|----------|
| Where does the unified pipeline live? | New module at root level (e.g. `pipeline.py` or `scan/core.py`). Not inside `benchmarking/`. |
| What does it return? | A result dataclass with normalized boxes, detections, face embeddings, autolink pairs, timing, and candidates. Rich enough for benchmarking, sliceable for production. |
| Where do `BibBox` / `FaceBox` move? | Out of `benchmarking/ground_truth.py` into the pipeline module (or `geometry.py`). They're pipeline output types, not benchmarking-specific. Ground truth still uses them — it imports from the new home. |
| Where does `autolink.py` move? | Out of `faces/` into the pipeline module. It's a bib+face step, not a face step. |
| What happens to `scan/pipeline.py`? | Becomes a thin wrapper: calls `run_single_photo()`, persists result to DB, saves artifacts. |
| What happens to `benchmarking/runner.py`? | `_run_bib_detection()` and `_run_face_detection()` are replaced by `run_single_photo()`. Runner adds scoring, candidate tracing, and JSON persistence on top. |
| Face fallback chain? | Moves into the unified pipeline. Both production and benchmarking get it. |
| Configurable `detect_fn`? | Keep the injection point from benchmarking (`detect_fn` parameter) so tests can mock detection without loading EasyOCR. |
| Debug artifacts (gray bbox, candidate images, snippets)? | Optional — controlled by a flag or callback. Production can enable them; benchmarking always does. |

## Context

- `scan/pipeline.py` — production scan (305 lines). `process_image()` is the main function.
- `benchmarking/runner.py` — benchmark runner (~1000 lines). `_run_bib_detection()`, `_run_face_detection()`, `_run_detection_loop()` are the key functions.
- `faces/autolink.py` — `predict_links()`, currently only called by benchmark runner
- `benchmarking/ground_truth.py` — defines `BibBox` (line 76) and `FaceBox` (line 201)
- `benchmarking/runner.py:PhotoResult` — the per-photo result type used by benchmarking
- `detection/detector.py` — `detect_bib_numbers()`, the actual OCR function
- `faces/backend.py` — `FaceBackend` protocol, `get_face_backend()`
- `faces/embedder.py` — `FaceEmbedder` protocol, `get_face_embedder()`
- `config.py` — all detection thresholds and fallback settings

## Changes (high level)

### New: unified pipeline module

A `run_single_photo()` function that:

1. Decodes image once
2. Detects bibs → normalizes to `BibBox` list
3. Detects faces with fallback chain → normalizes to `FaceBox` list
4. Embeds accepted faces
5. Links bibs ↔ faces via `predict_links()`
6. Returns a rich result object

### Moved: `BibBox`, `FaceBox`

Out of `benchmarking/ground_truth.py` into the pipeline module. `ground_truth.py` imports them from the new location. All other importers updated.

### Moved: `predict_links()` (from `faces/autolink.py`)

Into the pipeline module. It's a pipeline step, not a face-specific function.

### Modified: `scan/pipeline.py`

`process_image()` calls `run_single_photo()` then persists the result to DB. The face fallback chain, image decoding, and detection logic are removed (now in the shared pipeline).

### Modified: `benchmarking/runner.py`

`_run_bib_detection()` and `_run_face_detection()` are replaced by a call to `run_single_photo()`. The runner adds scoring on top. `_run_detection_loop()` simplifies significantly.

### Modified: DB layer

Add a `bib_face_links` table (or similar) so production can persist autolink results. Minimal schema: `photo_id`, `bib_detection_id`, `face_detection_id`, `provenance`.

## Tests

- Existing tests for `detect_bib_numbers`, `predict_links`, face detection backends continue to work (they test components, not the pipeline)
- `tests/test_autolink.py` — update imports
- `tests/test_runner.py` — update to use unified pipeline; scoring tests stay
- New `tests/test_pipeline.py` — test `run_single_photo()` with mocked detection
- Many import-path updates across test files for `BibBox`/`FaceBox`

## Verification

```bash
venv/bin/python -m pytest -v
```

After this task, running `venv/bin/python bnr.py scan` should produce bib-face links in the database (not just bibs and faces separately).

## Pitfalls

- **Massive import update**: `BibBox` and `FaceBox` are imported in ~30 files. Use a re-export in `benchmarking/ground_truth.py` during migration to avoid a flag-day change, then clean up.
- **`PhotoResult` evolution**: benchmarking's `PhotoResult` has scoring fields (TP/FP/FN counts, scorecard) that don't belong in the pipeline result. Keep `PhotoResult` as a benchmarking wrapper around the pipeline result.
- **Tuning task compatibility**: tasks 071–077 modify `_run_bib_detection()`, `_run_face_detection()`, and `_run_detection_loop()`. After this task, those functions either don't exist or are thin wrappers. Tuning tasks need updating to target the unified pipeline instead.
- **Face fallback config**: production uses `config.FACE_FALLBACK_BACKEND`, `config.FACE_DNN_FALLBACK_CONFIDENCE_MIN`, etc. These must flow through to the unified pipeline.
- **`detect_fn` injection**: benchmarking injects a mock `detect_fn` for testing. The unified pipeline should accept this too.

## Acceptance criteria

- [ ] One `run_single_photo()` function used by both production scan and benchmark runner
- [ ] `BibBox` and `FaceBox` defined outside `benchmarking/`
- [ ] `predict_links()` called by both production and benchmarking paths
- [ ] Production scan stores bib-face links in the database
- [ ] `scan/pipeline.py` no longer contains detection/normalization logic (delegates to shared pipeline)
- [ ] `benchmarking/runner.py` no longer contains detection/normalization logic (delegates to shared pipeline)
- [ ] Face fallback chain available in both paths
- [ ] All existing tests pass
- [ ] `venv/bin/python bnr.py scan --rescan <hash>` produces links

## Scope boundaries

- **In scope**: unified pipeline function, type relocation, autolink wiring, DB link storage, import updates
- **Out of scope**: cross-photo phase (clustering, refinement loop), tuning task updates (separate PRs), UI changes, benchmark scoring logic
- **Do not** change detection algorithms or thresholds — behavior should be identical, just unified
