# Task 037: Migrate remaining dataclasses to Pydantic across the codebase

Standalone. Can run concurrently with task-034 (runner migration) but share the same
patterns — do not start while task-034 is in flight.

## Goal

Eliminate `to_dict` / `from_dict` boilerplate in dataclasses outside `runner.py` by
converting value types to `pydantic.BaseModel`. This is the companion to task-034.

## Background

A codebase scan found 46 `@dataclass` uses across 13 files. Of these, roughly 20 have
manual `to_dict` / `from_dict` methods. Pydantic is already the project standard for
value types (`schemas.py`, `ground_truth.py`). The migration makes serialization
consistent and removes mechanical code.

## Scope

Work through the files in the order listed. Each section is independently committable.

---

### 1. `benchmarking/scoring.py` — BibScorecard, FaceScorecard, LinkScorecard

**Classes**: `BibScorecard`, `FaceScorecard`, `LinkScorecard`

**Special handling** — computed metrics:

These scorecards have `@property` methods (precision, recall, f1, ocr_accuracy) that
`to_dict()` currently writes into the JSON alongside the stored fields. The JSON is
consumed by the benchmark UI for display. The computed values must continue to appear
in `model_dump()` output.

Use `@computed_field` (Pydantic v2) so they are included in serialization:

```python
from pydantic import BaseModel, computed_field

class BibScorecard(BaseModel):
    detection_tp: int
    ...

    @computed_field
    @property
    def detection_precision(self) -> float:
        return _safe_div(self.detection_tp, self.detection_tp + self.detection_fp)
```

On `model_validate(data)`, Pydantic ignores any incoming `detection_precision` key (it's
computed, not a stored field), so existing JSON files load cleanly.

`MatchResult` (internal greedy-match result, never serialized) — **leave as dataclass**.

**TDD**: No new custom logic. Verify existing tests pass. If there are no existing tests
for scorecard construction, add one round-trip test per class.

---

### 2. `benchmarking/ghost.py` — Provenance, BibSuggestion, FaceSuggestion, PhotoSuggestions

**Classes**: `Provenance`, `BibSuggestion`, `FaceSuggestion`, `PhotoSuggestions`

**Special handling**:

- `BibSuggestion.has_coords` and `FaceSuggestion.has_coords` are `@property` returning a
  boolean — keep as `@property` (not `@computed_field`; these are logic helpers, not
  serialized fields).

- `PhotoSuggestions.from_dict` has an unusual signature:
  `from_dict(cls, content_hash: str, data: dict)`. The content_hash is passed separately
  from the data dict. Replace call-sites to pass it inside the dict, or use a
  `@classmethod` wrapper over `model_validate` that merges the arguments. Either
  approach is fine; document the choice.

`SuggestionStore` (mutable CRUD container) — **leave as dataclass**.

**TDD**: No new custom logic. Verify existing tests pass.

---

### 3. `benchmarking/sets.py` — BenchmarkSnapshotMetadata

**Class**: `BenchmarkSnapshotMetadata`

Simple migration — four plain fields, no custom validators needed.

`BenchmarkSnapshot` (has `save()` / `load()` service methods and a `@property path`) —
**leave as dataclass**. It's a service object, not a value type.

**TDD**: No new custom logic. Verify existing tests pass.

---

### 4. `benchmarking/face_embeddings.py` — IdentityMatch

**Class**: `IdentityMatch`

**Special handling** — similarity rounding:

The existing `to_dict()` rounds `similarity` to 4 decimal places. Replace with a
`@field_serializer`:

```python
from pydantic import BaseModel, field_serializer

class IdentityMatch(BaseModel):
    identity: str
    similarity: float
    content_hash: str
    box_index: int

    @field_serializer("similarity")
    def round_similarity(self, v: float) -> float:
        return round(v, 4)
```

`EmbeddingIndex` (holds a `np.ndarray` field, is an in-memory index with a `size`
property, never serialized to JSON) — **leave as dataclass**.

**TDD**: Write a red test for the `similarity` rounding before implementing.

---

### 5. `faces/types.py` — FaceModelInfo, FaceCandidate

**Classes**: `FaceModelInfo`, `FaceCandidate`

**Special handling**:

- `FaceModelInfo.from_dict` coerces `embedding_dim` with `int(data["embedding_dim"])`.
  Add a `@field_validator("embedding_dim", mode="before")` to coerce. TDD required.
- `FaceCandidate` has `FaceModelInfo` as a nested field — handled automatically by
  Pydantic nested model validation.
- Both are currently `frozen=True`; use `model_config = ConfigDict(frozen=True)`.

`FaceDetection` — **exclude from this task**. It holds a `numpy.ndarray` embedding
field and its `to_dict()` has an `include_embedding: bool` parameter that controls
whether the large embedding array is serialized. This conditional serialization has no
clean Pydantic equivalent. Migrate separately in a future task if needed.

**TDD**: Write a red test for `embedding_dim` int coercion.

---

### 6. `detection/types.py` — Detection

**Class**: `Detection`

`Detection` has `to_dict` / `from_dict` and a `scale_bbox()` instance method. The
method stays as-is; only the serialization boilerplate is replaced.

`BibCandidate` (no `to_dict`/`from_dict`, rich geometry methods: `to_xywh()`,
`extract_region()`) — **leave as dataclass**.

**TDD**: No new custom logic. Verify existing tests pass.

---

## Explicit exclusions and rationale

| Class | File | Reason excluded |
|---|---|---|
| `MatchResult` | scoring.py | Internal only; never serialized |
| `SuggestionStore` | ghost.py | Mutable CRUD container, not a value type |
| `BenchmarkSnapshot` | sets.py | Service object with load/save methods |
| `EmbeddingIndex` | face_embeddings.py | Holds numpy array; in-memory only |
| `FaceDetection` | faces/types.py | numpy field + conditional embedding serialization |
| `BibCandidate` | detection/types.py | No serialization needed; rich geometry methods |
| `BibGroundTruth` | ground_truth.py | Mutable CRUD container |
| `FaceGroundTruth` | ground_truth.py | Mutable CRUD container |
| `LinkGroundTruth` | ground_truth.py | Mutable CRUD container |
| `PreprocessConfig` | preprocessing/config.py | Frozen config with `validate()` domain logic |
| `PreprocessResult` | preprocessing/config.py | Complex coordinate-mapping methods |
| Preprocessing steps | preprocessing/steps.py | Frozen functional types (`apply()` interface) |
| `OpenCVHaar/DnnBackend` | faces/backend.py | Service objects: `__post_init__` loads ML models |
| `PixelEmbedder` | faces/embedder.py | Service object: lazy-loads model |
| `FaceNetEmbedder` | faces/embedder.py | Service object: lazy-loads model |
| `Photo` | photo.py | Has `from_db_row()` DB-specific logic |

## TDD constraint

- Do not change existing tests.
- For each piece of custom logic (validator, serializer, coercion) listed above, write a
  **red test first**, then implement.
- For purely mechanical migrations (no custom logic), no new tests are required beyond
  confirming existing tests continue to pass.

## Files

- `benchmarking/scoring.py`
- `benchmarking/ghost.py`
- `benchmarking/sets.py`
- `benchmarking/face_embeddings.py`
- `faces/types.py`
- `detection/types.py`
- `tests/test_pydantic_migration.py` — new, TDD tests for custom logic cases only
