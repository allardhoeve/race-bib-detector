# Task 056: Refactor `association_photo` to use `resolve_photo_nav()`

Depends on task-054.

## Goal

Replace the inline hash-resolution and navigation code in `association_photo()` with a call to `resolve_photo_nav()`. Clean up imports that are no longer needed directly in `labeling.py`.

## Problem

`association_photo()` (labeling.py:282–368) duplicates the same frozen-redirect + hash-resolution pattern as `bib_photo` and `face_photo`, but with a few differences:

1. Uses `_get_association_hashes(filter_type)` instead of `get_filtered_hashes()`
2. Filter suffix is `''` when `filter_type == 'all'`, not `?filter=all`
3. Has TWO next-unlabeled searches: `next_unlabeled_url` (unlinked) and `next_incomplete_url` (underlinked)
4. Loads additional data: bib GT, face GT, link GT, bib_boxes, face_boxes, links
5. Loads `photo_path` from `all_index[full_hash]`

The nav helper handles differences 1–2 via its `filter_suffix` parameter. Differences 3–5 remain handler-specific.

## Context — current handler

### `association_photo()` (labeling.py:282–368, 87 lines)

```python
# :290–299  Frozen redirect (same pattern as bib/face)
all_index = load_photo_index()
resolved = find_hash_by_prefix(content_hash, set(all_index.keys()))
if resolved:
    frozen_set = is_frozen(resolved)
    if frozen_set:
        return RedirectResponse(...)

# :301–304  Hash resolution from filtered list
all_hashes = _get_association_hashes(filter_type)
full_hash = find_hash_by_prefix(content_hash, all_hashes)
if not full_hash:
    raise HTTPException(404)

# :306–308  Photo path lookup from index
index = all_index
photo_paths = index[full_hash]
photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths

# :310–322  Load bib/face/link GT (handler-specific)
bib_gt = load_bib_ground_truth()
face_gt = load_face_ground_truth()
link_gt = load_link_ground_truth()
...

# :324–336  Navigation (same pattern)
idx = all_hashes.index(full_hash)
total = len(all_hashes)
filter_suffix = f'?filter={filter_type}' if filter_type != 'all' else ''
prev_url = ... if idx > 0 else None
next_url = ... if idx < total - 1 else None

# :338–350  Two next-unlabeled searches (handler-specific)
next_unlabeled_url = None
for h in get_unlinked_hashes(): ...
next_incomplete_url = None
for h in get_underlinked_hashes(): ...

# :352–368  Render template
```

### Key difference from bib/face handlers

The `association_photo` handler builds `filter_suffix` differently:
```python
filter_suffix = f'?filter={filter_type}' if filter_type != 'all' else ''
```

This maps directly to `resolve_photo_nav()`'s `filter_suffix` parameter — just pass the computed string.

### Photo path lookup

After refactoring, `nav.all_index` provides the full index, so the photo path lookup becomes:
```python
photo_paths = nav.all_index[nav.full_hash]
photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths
```

## Changes

### Modified: `benchmarking/routes/ui/labeling.py`

#### Rewritten `association_photo()`:

```python
@ui_labeling_router.get('/associations/{content_hash}')
async def association_photo(content_hash: str, request: Request, filter_type: str = Query(default='all', alias='filter')):
    from benchmarking.ground_truth import load_link_ground_truth

    hashes = _get_association_hashes(filter_type)
    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    filter_suffix = f'?filter={filter_type}' if filter_type != 'all' else ''
    nav = resolve_photo_nav(content_hash, hashes, request, 'association_photo', filter_suffix)
    if isinstance(nav, RedirectResponse):
        return nav

    photo_paths = nav.all_index[nav.full_hash]
    photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths

    # Load GT data
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()
    ...  # rest unchanged

    return TEMPLATES.TemplateResponse(request, 'link_labeling.html', {
        'content_hash': nav.full_hash,
        'current': nav.idx + 1,
        'total': nav.total,
        'prev_url': nav.prev_url,
        'next_url': nav.next_url,
        ...  # rest of context unchanged
    })
```

#### Clean up imports

After this task, `is_frozen`, `load_photo_index`, and `find_hash_by_prefix` are no longer used directly in `labeling.py`. Remove them:

```python
# Remove:
from benchmarking.frozen_check import is_frozen
from benchmarking.photo_index import load_photo_index

# find_hash_by_prefix may still be used — check before removing
```

**Note**: `association_photo` currently has no empty-list guard at the top. The original code goes straight to hash resolution without checking `if not hashes`. Add this guard for consistency (the other two handlers have it). The nav helper will 404 anyway, but the guard is cleaner.

## Tests

No new tests. Verification:

```bash
venv/bin/python -m pytest tests/test_web_app.py -v
```

## Scope boundaries

- **In scope**: refactoring `association_photo()`, import cleanup
- **Out of scope**: `bib_photo`/`face_photo` (task-055), `frozen.py`, new tests (task-057)
- **Do not** change any external behaviour
