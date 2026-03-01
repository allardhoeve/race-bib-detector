# Task 045: Identity gallery frozen/new indicators

Depends on task-044 (frozen set enforcement). Extends task-043 (identity gallery).

## Goal

Add visual distinction in the identity gallery between face appearances from frozen (verified) photos and new (unfrozen) photos. This lets the labeler see which faces are already QA'd and focus review on new additions only.

## Background

After freezing a verified set of ~250 photos, the user will label ~200 more. The identity gallery groups all faces by identity across all photos. Without visual distinction, the user would have to re-review everything — including the already-verified faces. With frozen indicators, verified faces are visually muted, and new faces stand out.

## Context

- `benchmarking/services/identity_gallery_service.py` — `FaceAppearance`, `IdentityGroup`, `get_identity_gallery()`
- `benchmarking/frozen_check.py` (from task-044) — `is_frozen()`, `get_all_frozen_hashes()`
- `benchmarking/templates/identity_gallery.html` — gallery template

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Visual style | Frozen faces: slightly muted opacity or subtle border colour. New faces: normal style, possibly a small "new" badge |
| Sorting within identity | Frozen faces first, then new faces (stable sub-order by hash) |
| Filtering | Optional toggle: "Show all" / "Show new only" / "Show frozen only" |
| Click behaviour | Frozen faces still link to association page (read-only per task-044) |
| Summary stats | Per-identity: show count of frozen vs new appearances |

## Changes

### Modified: `benchmarking/services/identity_gallery_service.py`

Add `frozen: bool` field to `FaceAppearance`. In `get_identity_gallery()`, load frozen hashes once and set the flag per appearance.

```python
@dataclass
class FaceAppearance:
    content_hash: str
    face_box_index: int
    bib_number: str | None = None
    bib_box_index: int | None = None
    frozen: bool = False
```

Add summary properties to `IdentityGroup`:

```python
@property
def frozen_count(self) -> int: ...

@property
def new_count(self) -> int: ...
```

### Modified: `benchmarking/templates/identity_gallery.html`

- [ ] Each face card gets a CSS class (`frozen` / `new`) based on `appearance.frozen`
- [ ] Frozen cards: muted style (e.g. `opacity: 0.6` or grey border)
- [ ] New cards: normal style, optional accent border
- [ ] Per-identity header shows: `"Name (3 frozen, 2 new)"`
- [ ] Optional JS toggle to filter frozen/new/all

## Tests

Extend `tests/test_identity_gallery.py`:

- `test_face_appearance_frozen_flag_set()` — frozen snapshot hash → `frozen=True`
- `test_face_appearance_unfrozen_flag()` — hash not in any snapshot → `frozen=False`
- `test_identity_group_frozen_count()` — correct counts
- `test_identity_group_new_count()` — correct counts

## Scope boundaries

- **In scope**: frozen flag on FaceAppearance, visual styling, optional filter toggle
- **Out of scope**: editing from gallery, unfreezing, per-race scoping
- **Do not** modify frozen set infrastructure (task-044 owns that)
