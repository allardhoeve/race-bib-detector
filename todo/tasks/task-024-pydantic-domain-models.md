# Task 024: Migrate domain models to Pydantic BaseModel

Independent of tasks 019–022. Must be done before task-025.

## Goal

Replace the `@dataclass` definitions in `benchmarking/ground_truth.py` with
Pydantic `BaseModel` subclasses so that `to_dict()` / `from_dict()` methods
are eliminated and runtime validation is automatic.

## Background

The app has invented its own serialisation layer: every domain class has a
hand-written `to_dict()` method and a `from_dict()` classmethod. Together they
total ~150 lines of boilerplate. Pydantic's `BaseModel` replaces both for free:
`.model_dump()` replaces `to_dict()`, and `ModelClass(**data)` (or
`.model_validate(data)`) replaces `from_dict()`.

This is the foundational change before the Flask → FastAPI migration (task-025).
FastAPI requires Pydantic models for request/response validation; having the
domain models already in Pydantic means they can be used directly as response
bodies without an extra translation step.

Reviewed in the API design discussion: "The ground_truth.py dataclasses are doing
what Pydantic would do — and Pydantic is now a natural fit."

## Context

`ground_truth.py` defines these classes (currently `@dataclass`):

- `BibBox`
- `BibPhotoLabel`
- `FaceBox`
- `FacePhotoLabel`
- `BibFaceLink`
- `BibGroundTruth` (container — loads/saves JSON; may stay as dataclass)
- `FaceGroundTruth` (container — same)

The container classes (`BibGroundTruth`, `FaceGroundTruth`) hold the JSON load/save
logic and the `photos` dict. They can stay as dataclasses or plain classes for now
since they are not serialised over the wire. Focus this task on the wire-format
classes: `BibBox`, `FaceBox`, `BibPhotoLabel`, `FacePhotoLabel`, `BibFaceLink`.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Pydantic version | v2 (`pydantic>=2`) — already in use via FastAPI deps |
| `has_coords` computed property | Keep as `@property`; add `model_config = ConfigDict(arbitrary_types_allowed=True)` only if needed. `has_coords` does NOT need to appear in `.model_dump()` |
| `from_dict()` replacement | `FaceBox.model_validate(data)` — handles alias mapping and coercion |
| `to_dict()` replacement | `.model_dump()` — callers updated to use this |
| Enum validation for `scope` | Use `Literal` type annotations; Pydantic validates at construction |
| Mutable defaults (e.g. `boxes=[]`) | `Field(default_factory=list)` — same pattern as now |
| Test impact | Tests that call `.to_dict()` / `from_dict()` must be updated to `.model_dump()` / `.model_validate()` |

## Changes: `benchmarking/ground_truth.py`

### Remove imports

```python
# Remove:
from dataclasses import dataclass, field

# Add:
from pydantic import BaseModel, Field, ConfigDict, model_validator
```

### BibBox (representative example)

**Before:**
```python
@dataclass
class BibBox:
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"

    @property
    def has_coords(self) -> bool:
        return self.x is not None

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "number": self.number, "scope": self.scope}

    @classmethod
    def from_dict(cls, d: dict) -> "BibBox":
        return cls(x=d["x"], y=d["y"], w=d["w"], h=d["h"],
                   number=str(d.get("number", "")),
                   scope=d.get("scope", "bib"))
```

**After:**
```python
class BibBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"

    @property
    def has_coords(self) -> bool:
        return True  # all BibBox instances have coords by construction

    model_config = ConfigDict(extra="ignore")
```

Callers change from:
- `BibBox.from_dict(d)` → `BibBox.model_validate(d)`
- `box.to_dict()` → `box.model_dump()`

Apply the same pattern to `FaceBox`, `BibPhotoLabel`, `FacePhotoLabel`,
`BibFaceLink`.

### Special case: `has_coords` on FaceBox

`FaceBox.has_coords` is currently `False` for legacy boxes that lack coordinates.
Preserve this by keeping `x`, `y`, `w`, `h` as `float | None` with `None` as
default, and making `has_coords` a plain `@property`:

```python
class FaceBox(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str = "keep"
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def has_coords(self) -> bool:
        return self.x is not None

    model_config = ConfigDict(extra="ignore")
```

## Changes: call sites

Every call to `.to_dict()` or `from_dict()` in the route files must be updated.
Search with:

```
grep -rn "\.to_dict\(\)\|from_dict(" benchmarking/ tests/
```

Expected call sites:
- `routes_bib.py` — `BibBox.from_dict(b)`, `b.to_dict()`
- `routes_face.py` — `FaceBox.from_dict(b)`, `b.to_dict()`
- `ghost.py` — `BibSuggestion.to_dict()`, `FaceSuggestion.to_dict()`
- `scoring.py` — possibly reads box attributes directly (no change needed)
- `runner.py` — check for any serialisation calls

Mechanical replacement:
- `XBox.from_dict(d)` → `XBox.model_validate(d)`
- `obj.to_dict()` → `obj.model_dump()`

Do NOT change the JSON load/save functions (`load_bib_ground_truth`,
`save_face_ground_truth`, etc.) — they use `json.load` / `json.dump` and
already work with plain dicts. The only change is in the
`XGroundTruth.get_photo()` / `add_photo()` methods that construct model
instances from dicts.

## Changes: `tests/`

Run:
```
grep -rn "\.to_dict\(\)\|from_dict(" tests/
```

Update every test assertion:
- `box.to_dict()` → `box.model_dump()`
- `BibBox.from_dict(d)` → `BibBox.model_validate(d)`

## Tests

No new test files needed. Existing model tests implicitly cover Pydantic behaviour.

Verify after migration:
- All 250 existing tests pass.
- `BibBox.model_validate({"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4})` works.
- `FaceBox.model_validate({})` produces a box with `has_coords == False`.
- `box.model_dump()` returns a plain dict suitable for `json.dumps()`.

## Scope boundaries

- **In scope**: `BibBox`, `FaceBox`, `BibPhotoLabel`, `FacePhotoLabel`,
  `BibFaceLink` in `ground_truth.py`; all call sites in `benchmarking/` and
  `tests/`.
- **Out of scope**: Container classes (`BibGroundTruth`, `FaceGroundTruth`),
  `ghost.py` suggestion classes (`BibSuggestion`, `FaceSuggestion`) — migrate
  those in a follow-up if desired.
- **Do not** change the JSON file format on disk.
- **Do not** change any URL or HTTP method.
- **Do not** start task-025 until all 250 tests pass with Pydantic models.
