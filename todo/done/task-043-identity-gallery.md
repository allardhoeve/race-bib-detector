# Task 043: Identity gallery view

Read-only QA view. No dependencies on pending tasks.

## Goal

Add a page at `/identities/` that shows every labeled face grouped by identity, with linked bib crops and numbers alongside. This lets the labeler spot misattributed identities (e.g. two different people sharing an `anon-*` label) and incorrect face-bib links.

## Background

Face labeling has 137 named identities + 7 anonymous ones. Some `anon-*` entries may be mixed up due to mislabeling. There is currently no way to visually audit identity assignments across photos — you'd have to click through each photo one by one.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Layout | Single scrollable page, one row per identity |
| Card content | Face crop on top, bib crop below (if linked), bib number as text |
| Click target | Navigate to `/associations/{hash}` (link labeling page) |
| Sort order | Named identities alphabetically, then `anon-*` alphabetically, then `Unassigned` at bottom |
| Null identities | Shown as "Unassigned" group at bottom (can be removed later if useless) |
| Scope filter | Only `keep`-scoped face boxes with coordinates |
| Row overflow | Show all faces, let rows wrap naturally |
| No bib link | Card shows face crop only (shorter card, no label) |
| Home page link | "QA Tools" section below the workflow cards |

## Changes

### New: `benchmarking/services/bib_service.py`

Bib crop helper, mirroring `face_service.get_face_crop_jpeg()`:

```python
def get_bib_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
    """Return JPEG bytes of a labeled bib crop, or None if not found."""
    # Same pattern as face_service: load GT → get box → crop → JPEG
```

### Modified: `benchmarking/routes/api/bibs.py`

Add endpoint:

```python
@api_bibs_router.get('/api/bibs/{content_hash}/crop/{box_index}')
async def bib_crop(content_hash: str, box_index: int):
    """Serve a bib box crop as JPEG."""
```

### New: `benchmarking/services/identity_gallery_service.py`

Aggregation logic:

```python
@dataclass
class FaceAppearance:
    content_hash: str
    face_box_index: int
    bib_number: str | None    # e.g. "42" or None if no link
    bib_box_index: int | None # for bib crop URL

@dataclass
class IdentityGroup:
    name: str          # identity name, or "Unassigned"
    faces: list[FaceAppearance]

def get_identity_gallery() -> list[IdentityGroup]:
    """Return all identities with their face+bib appearances.

    1. Load face_ground_truth, bib_ground_truth, link_ground_truth
    2. For each photo in face GT, for each box with has_coords and scope=="keep":
       - Find linked bib via link GT (face_index match)
       - Get bib number from bib GT
    3. Group by identity (None → "Unassigned")
    4. Sort: named → anon-* → Unassigned
    """
```

### Modified: `benchmarking/routes/ui/labeling.py`

Add route:

```python
@ui_labeling_router.get('/identities/')
async def identity_gallery(request: Request):
    """Identity gallery: all faces grouped by identity with linked bibs."""
    from benchmarking.services.identity_gallery_service import get_identity_gallery
    groups = get_identity_gallery()
    return TEMPLATES.TemplateResponse(request, 'identity_gallery.html', {
        'groups': groups,
        'total_identities': len(groups),
    })
```

### New: `benchmarking/templates/identity_gallery.html`

Extends `base.html`. Structure:

- Header: title + back link to home
- For each `IdentityGroup`: heading with name + face count, then horizontal flex row of cards
- Each card: `<a href="/associations/{hash}">` wrapping face crop `<img>` + bib crop `<img>` + bib number text
- All `<img>` tags use `loading="lazy"` (140+ identities = many images)
- Dark theme consistent with existing pages

### Modified: `benchmarking/templates/labels_home.html`

Add a "QA Tools" section below the workflow cards with an "Identity Gallery" link.

## Tests

Add `tests/test_identity_gallery.py`:

- `test_get_identity_gallery_groups_by_identity()` — three faces across two identities → correct grouping
- `test_get_identity_gallery_excludes_non_keep_scope()` — `exclude`/`uncertain` boxes omitted
- `test_get_identity_gallery_null_identity_grouped_as_unassigned()` — null → "Unassigned" at end
- `test_get_identity_gallery_sort_order()` — named < anon-* < Unassigned
- `test_get_identity_gallery_resolves_bib_link()` — linked face shows bib number + index
- `test_bib_crop_endpoint_returns_jpeg()` — integration test for `/api/bibs/{hash}/crop/{index}`
- `test_identity_gallery_page_renders()` — `GET /identities/` returns 200

## Scope boundaries

- **In scope**: read-only gallery view, bib crop endpoint, aggregation service
- **Out of scope**: editing identities from this view, face crop caching, pagination
- **Do not** modify ground truth schema or existing labeling flows
