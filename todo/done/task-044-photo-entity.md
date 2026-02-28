# Task 044: Extract Photo entity from scattered GT fields

Prerequisite for task-046 (frozen enforcement). Independent of task-045.

## Goal

Create a first-class `PhotoMetadata` model and a single `photo_metadata.json` file that holds all photo-level properties currently scattered across the bib GT, face GT, and photo index. This gives us a clean place to add `frozen` (in task-046) without polluting labeling schemas.

## Background

Photo-level data is currently spread across three places:
- `BibPhotoLabel.split` — train/test grouping, a photo property
- `BibPhotoLabel.tags` — photo-level bib condition tags (`obscured_bib`, `dark_bib`, etc.)
- `FacePhotoLabel.tags` — photo-level face condition tags (`no_faces`, `light_faces`)
- `photo_index.json` — maps content hash → file paths on disk

None of these belong on a labeling dimension. They describe the photo itself.

## Context

- `benchmarking/ground_truth.py` — `BibPhotoLabel` (has `split`, `tags`), `FacePhotoLabel` (has `tags`)
- `benchmarking/photo_index.py` — `load_photo_index()`, `save_photo_index()`, `get_path_for_hash()`
- `benchmarking/scanner.py` — `build_photo_index()` scans disk
- 15+ files consume `load_photo_index()` — need a compat wrapper
- `BIB_PHOTO_TAGS`: `obscured_bib`, `dark_bib`, `no_bib`, `blurry_bib`, `partial_bib`, `light_bib`, `other_banners`
- `FACE_PHOTO_TAGS`: `no_faces`, `light_faces`

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Storage | Single `photo_metadata.json` replaces `photo_index.json` |
| Model | `PhotoMetadata` Pydantic model with `paths`, `split`, `bib_tags`, `face_tags` |
| Tag separation | Keep `bib_tags` and `face_tags` as separate fields — they're set at different times in different labeling flows and have separate validation sets |
| `frozen` field | Added in task-046, not here. But the model is designed to accommodate it |
| Index compat | `load_photo_index()` becomes a thin wrapper over the new format, returning `dict[str, list[str]]` as before. Existing consumers don't break |
| `labeled` stays | `labeled` remains on bib/face labels — it's per-dimension, not per-photo |
| Unlabeled photos | Photos with only `paths` and no tags/split get default empty values. All 702 photos appear in the file |
| Tag validation | `BIB_PHOTO_TAGS` and `FACE_PHOTO_TAGS` constants stay in `ground_truth.py`, validation moves to `PhotoMetadata` |

## Changes

### New: `benchmarking/photo_metadata.py`

```python
class PhotoMetadata(BaseModel):
    """Photo-level properties, independent of any labeling dimension."""
    paths: list[str]           # relative paths from benchmarking/photos/
    split: str = ""            # train/test grouping (e.g. "iteration", "full")
    bib_tags: list[str] = []   # photo-level bib condition tags
    face_tags: list[str] = []  # photo-level face condition tags
    # frozen: str | None = None  — added in task-046


class PhotoMetadataStore(BaseModel):
    """Container for all photo metadata, keyed by content hash."""
    version: int = 1
    photos: dict[str, PhotoMetadata] = {}

    def get(self, content_hash: str) -> PhotoMetadata | None: ...
    def set(self, content_hash: str, meta: PhotoMetadata) -> None: ...


def load_photo_metadata(path: Path | None = None) -> PhotoMetadataStore: ...
def save_photo_metadata(store: PhotoMetadataStore, path: Path | None = None) -> None: ...
```

On disk (`photo_metadata.json`):
```json
{
  "version": 1,
  "photos": {
    "006c6313...": {
      "paths": ["clubkampioenschappen/HVV_3680.jpg"],
      "split": "iteration",
      "bib_tags": ["obscured_bib"],
      "face_tags": []
    },
    "abc12345...": {
      "paths": ["clubkampioenschappen/HVV_3700.jpg"],
      "split": "",
      "bib_tags": [],
      "face_tags": ["no_faces"]
    }
  }
}
```

### Modified: `benchmarking/photo_index.py`

Replace internals with a compat wrapper:

```python
def load_photo_index(path=None) -> dict[str, list[str]]:
    """Compat: loads photo_metadata.json, returns {hash: paths} dict."""
    store = load_photo_metadata(path)
    return {h: m.paths for h, m in store.photos.items()}

def save_photo_index(index, path=None) -> None:
    """Compat: updates paths in photo_metadata.json."""
    ...

def get_path_for_hash(content_hash, photos_dir, index=None) -> Path | None:
    """Unchanged API, reads from new format internally."""
    ...
```

Existing consumers (15+ files) continue calling `load_photo_index()` — no changes needed.

### Modified: `benchmarking/scanner.py`

`build_photo_index()` returns the same `dict[str, list[str]]` as before. The caller (`prepare.py`) wraps it into `PhotoMetadata` entries when saving.

### Modified: `benchmarking/prepare.py`

`prepare_benchmark()` writes `photo_metadata.json` instead of `photo_index.json`. Creates `PhotoMetadata` entries with `paths` populated, other fields default.

### Modified: `benchmarking/ground_truth.py`

**`BibPhotoLabel`**: remove `split` and `tags` fields.
```python
class BibPhotoLabel(BaseModel):
    content_hash: str = ""
    boxes: list[BibBox] = []
    labeled: bool = False
    # split and tags removed — now on PhotoMetadata
```

**`FacePhotoLabel`**: remove `tags` field.
```python
class FacePhotoLabel(BaseModel):
    content_hash: str = ""
    boxes: list[FaceBox] = []
    labeled: bool = False
    # tags removed — now on PhotoMetadata
```

**`BibGroundTruth.from_dict()`** and **`FaceGroundTruth.from_dict()`**: on load, silently ignore `split`/`tags` fields in old JSON files (already handled by `extra="ignore"`).

**`BibGroundTruth.to_dict()`** and **`FaceGroundTruth.to_dict()`**: stop writing `split`/`tags`.

### Migration script: `benchmarking/migrate_photo_metadata.py`

One-time script, run once and commit the result. Not an auto-migration on load.

Steps:
1. Load `photo_index.json` → get paths
2. Load `bib_ground_truth.json` → extract `split` and `tags` per photo
3. Load `face_ground_truth.json` → extract `tags` per photo
4. Build `PhotoMetadataStore` with all data merged
5. Save `photo_metadata.json`
6. Re-save bib GT and face GT without `split`/`tags` (they'll be dropped by the updated `to_dict()`)
7. Delete `photo_index.json` (replaced by `photo_metadata.json`)

Run: `venv/bin/python -m benchmarking.migrate_photo_metadata`
Then commit the new `photo_metadata.json`, updated GT files, and deleted `photo_index.json`.

### Modified: labeling UI save handlers

Bib labeling save: writes bib boxes to bib GT, writes `bib_tags` + `split` to `PhotoMetadata`.
Face labeling save: writes face boxes to face GT, writes `face_tags` to `PhotoMetadata`.

This means the save endpoints now write to two files. The API request body for bibs still includes `tags` and `split` — the route handler splits them between the two stores.

### Modified: labeling UI load handlers

Bib labeling load: reads bib GT for boxes + labeled, reads `PhotoMetadata` for `split` and `bib_tags`.
Face labeling load: reads face GT for boxes + labeled, reads `PhotoMetadata` for `face_tags`.

### Modified: `benchmarking/schemas.py`

`GetBibBoxesResponse`: keep `tags` and `split` fields (they come from PhotoMetadata now, but the API shape doesn't change).
`GetFaceBoxesResponse`: keep `tags` field.

No schema changes visible to the frontend.

### Modified: `benchmarking/completeness.py`

Remove any reference to `split` from completeness model if present. Completeness checks `labeled` on bib/face GT (unchanged).

### Modified: `benchmarking/runner.py`

Currently calls `get_by_split()` on bib GT which filters by `BibPhotoLabel.split`. This needs to filter by `PhotoMetadata.split` instead.

## Tests

Add `tests/test_photo_metadata.py`:

- `test_photo_metadata_roundtrip()` — save and load preserves all fields
- `test_photo_metadata_defaults()` — missing fields get correct defaults
- `test_photo_metadata_store_get_set()` — get/set operations work
- `test_load_photo_index_compat()` — compat wrapper returns `dict[str, list[str]]`
- `test_get_path_for_hash_compat()` — path lookup works through new format

Add `tests/test_migration.py`:

- `test_migrate_merges_index_and_gt()` — migration correctly merges all three sources
- `test_migrate_preserves_all_tags()` — no tags lost during migration
- `test_migrate_preserves_all_splits()` — no splits lost during migration

Modify existing tests:

- `tests/test_ground_truth.py` — update tests that reference `BibPhotoLabel.tags` or `.split`
- `tests/test_runner.py` / `tests/test_runner_models.py` — update `get_by_split()` usage

## Scope boundaries

- **In scope**: PhotoMetadata model, photo_metadata.json, migration script, compat wrappers, update save/load handlers, remove split/tags from GT labels
- **Out of scope**: `frozen` field (task-046), frozen enforcement, frozen viewer
- **Do not** change the API request/response shapes — frontend sees the same fields
