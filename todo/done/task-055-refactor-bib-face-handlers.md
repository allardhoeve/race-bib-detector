# Task 055: Refactor `bib_photo` and `face_photo` to use `resolve_photo_nav()`

Depends on task-054.

## Goal

Replace the duplicated hash-resolution and navigation code in `bib_photo()` and `face_photo()` with calls to `resolve_photo_nav()`. Each handler should shrink from ~80 lines to ~35 lines.

## Problem

After task-054 creates the `resolve_photo_nav()` helper, the two bib/face handlers still contain the old inline navigation code. This task rewrites them to use the helper.

## Context — current handlers

### `bib_photo()` (labeling.py:53–135, 82 lines)

Lines 64–103 are the duplicated nav block (extracted by task-054). After the nav block, the handler-specific logic is:

```python
# :79–88  Load bib GT, metadata, determine default split
bib_gt = load_bib_ground_truth()
label = bib_gt.get_photo(full_hash)
meta_store = load_photo_metadata()
meta = meta_store.get(full_hash)
default_split = ...

# :105–114  Build next_unlabeled_url (bib-specific)
all_hashes_sorted = sorted(all_index.keys())
def _bib_is_labeled(h): ...
next_unlabeled_url = find_next_unlabeled_url(...)

# :116–117  Latest run ID
runs = list_runs()
latest_run_id = runs[0]['run_id'] if runs else None

# :119–135  Render template with full context dict
return TEMPLATES.TemplateResponse(request, 'labeling.html', { ... })
```

### `face_photo()` (labeling.py:153–236, 83 lines)

Structurally identical to `bib_photo` except:
- Uses `get_filtered_face_hashes()` instead of `get_filtered_hashes()`
- Loads face GT instead of bib GT
- Uses `is_face_labeled()` for next-unlabeled logic
- Renders `face_labeling.html` with face-specific context (face_count, face_tags, face_box_tags)

### Imports already available

```python
from benchmarking.label_utils import find_hash_by_prefix, find_next_unlabeled_url, ...
from benchmarking.photo_index import load_photo_index
from benchmarking.frozen_check import is_frozen
```

After task-054, add:
```python
from benchmarking.routes.ui.nav import resolve_photo_nav, PhotoNavContext
```

## Changes

### Modified: `benchmarking/routes/ui/labeling.py`

Add import at top:
```python
from benchmarking.routes.ui.nav import resolve_photo_nav, PhotoNavContext
```

Remove imports that become unused after refactor:
```python
# These are now only used inside resolve_photo_nav:
# from benchmarking.frozen_check import is_frozen       — remove if no other use
# from benchmarking.photo_index import load_photo_index  — remove if no other use
```

**Note**: `load_photo_index` is still needed by `association_photo` until task-056 lands. `is_frozen` and `find_hash_by_prefix` are also still used by `association_photo`. So only clean up unused imports after task-056 is done (or leave them — the linter will flag them).

#### Rewritten `bib_photo()`:

```python
@ui_labeling_router.get('/bibs/{content_hash}')
async def bib_photo(content_hash: str, request: Request, filter_type: str = Query(default='all', alias='filter')):
    hashes = get_filtered_hashes(filter_type)
    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    nav = resolve_photo_nav(content_hash, hashes, request, 'bib_photo', f'?filter={filter_type}')
    if isinstance(nav, RedirectResponse):
        return nav

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(nav.full_hash)

    meta_store = load_photo_metadata()
    meta = meta_store.get(nav.full_hash)
    if meta and meta.split:
        default_split = meta.split
    else:
        default_split = 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'

    all_hashes_sorted = sorted(nav.all_index.keys())
    def _bib_is_labeled(h): return bool((lbl := bib_gt.get_photo(h)) and lbl.labeled)
    next_unlabeled_url = find_next_unlabeled_url(
        nav.full_hash, all_hashes_sorted, _bib_is_labeled,
        lambda h: str(request.url_for('bib_photo', content_hash=h)) + f'?filter={filter_type}',
    )

    runs = list_runs()
    latest_run_id = runs[0]['run_id'] if runs else None

    return TEMPLATES.TemplateResponse(request, 'labeling.html', {
        'content_hash': nav.full_hash,
        'bibs_str': ', '.join(str(b) for b in label.bibs) if label else '',
        'tags': meta.bib_tags if meta else [],
        'split': default_split,
        'all_tags': sorted(ALLOWED_TAGS),
        'current': nav.idx + 1,
        'total': nav.total,
        'has_prev': nav.idx > 0,
        'has_next': nav.idx < nav.total - 1,
        'prev_url': nav.prev_url,
        'next_url': nav.next_url,
        'next_unlabeled_url': next_unlabeled_url,
        'filter': filter_type,
        'latest_run_id': latest_run_id,
        'workflow': workflow_context_for(nav.full_hash, 'bibs'),
    })
```

#### Rewritten `face_photo()`:

Same pattern — replace the inline nav block with `resolve_photo_nav()`, use `nav.*` fields for template context.

## Tests

No new tests. Task-054 tests the helper. Task-057 tests the handlers end-to-end.

Verification: run the existing test suite to confirm no regressions:

```bash
venv/bin/python -m pytest tests/test_web_app.py -v
```

## Scope boundaries

- **In scope**: refactoring `bib_photo()` and `face_photo()` only
- **Out of scope**: `association_photo()` (task-056), `frozen_photo_detail()` (leave as-is), new tests (task-057)
- **Do not** change any external behaviour — same URLs, same redirects, same template contexts
