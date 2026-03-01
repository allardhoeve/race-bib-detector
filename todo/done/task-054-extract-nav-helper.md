# Task 054: Extract `resolve_photo_nav()` helper

Independent of other open tasks. No prerequisites.

## Goal

Extract the repeated hash-resolution + frozen-redirect + prev/next navigation logic from the labeling handlers into a single reusable helper, so that tasks 055 and 056 can refactor the handlers to use it.

## Problem

`benchmarking/routes/ui/labeling.py` (368 lines) contains three handlers — `bib_photo()` (:53), `face_photo()` (:153), `association_photo()` (:282) — that each repeat the same ~25-line block:

1. `load_photo_index()` → `find_hash_by_prefix(content_hash, set(all_index.keys()))`
2. `is_frozen(full_hash)` → `RedirectResponse` to `frozen_photo_detail`
3. `find_hash_by_prefix(content_hash, hashes)` → 404 if not found
4. `hashes.index(full_hash)` → compute `idx`, `total`, `prev_url`, `next_url`

Steps 1–4 are identical across all three handlers (only the route name and filter suffix differ).

## Context — current code

### The duplicated pattern (from `bib_photo`, :64–103)

```python
# Step 1: resolve from full index
all_index = load_photo_index()
full_hash = find_hash_by_prefix(content_hash, set(all_index.keys()))

# Step 2: frozen redirect
if full_hash:
    frozen_set = is_frozen(full_hash)
    if frozen_set:
        return RedirectResponse(
            url=str(request.url_for('frozen_photo_detail', set_name=frozen_set, content_hash=full_hash[:8])),
            status_code=302,
        )

# Step 3: resolve from filtered hashes
full_hash = find_hash_by_prefix(content_hash, hashes)
if not full_hash:
    raise HTTPException(status_code=404, detail='Photo not found')

# Step 4: navigation
idx = hashes.index(full_hash)
total = len(hashes)
has_prev = idx > 0
has_next = idx < total - 1
prev_url = str(request.url_for('bib_photo', content_hash=hashes[idx - 1][:8])) + f'?filter={filter_type}' if has_prev else None
next_url = str(request.url_for('bib_photo', content_hash=hashes[idx + 1][:8])) + f'?filter={filter_type}' if has_next else None
```

The same structure appears at `face_photo` (:165–203) and `association_photo` (:291–336).

### Files involved

- `benchmarking/routes/ui/labeling.py` — the three handlers (source of duplication)
- `benchmarking/routes/ui/frozen.py` — `frozen_photo_detail()` uses similar but different navigation (frozen set context, no frozen redirect); **leave as-is**
- `benchmarking/label_utils.py:75` — `find_hash_by_prefix()` (used by the pattern)
- `benchmarking/frozen_check.py` — `is_frozen()` (used by the pattern)
- `benchmarking/photo_index.py` — `load_photo_index()` (used by the pattern)

### Existing helpers in `label_utils.py`

```python
find_hash_by_prefix(prefix, hashes) -> str | None        # :75
find_next_unlabeled_url(full_hash, sorted, fn, url_fn)   # :58
get_filtered_hashes(filter_type) -> list[str]             # :31
get_filtered_face_hashes(filter_type) -> list[str]        # :47
filter_results(results, filter_type)                       # :91
```

## Changes

### New: `benchmarking/routes/ui/nav.py`

```python
"""Shared hash resolution + navigation for photo detail pages."""

from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.responses import RedirectResponse

from benchmarking.frozen_check import is_frozen
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index


@dataclass
class PhotoNavContext:
    """Resolved hash + navigation state for a photo detail page."""
    full_hash: str
    idx: int             # 0-based position in filtered list
    total: int
    prev_url: str | None
    next_url: str | None
    all_index: dict      # full photo index (for next-unlabeled lookups)


def resolve_photo_nav(
    content_hash: str,
    filtered_hashes: list[str],
    request: Request,
    route_name: str,
    filter_suffix: str = '',
) -> PhotoNavContext | RedirectResponse:
    """Resolve hash prefix, check frozen, build prev/next navigation.

    Returns RedirectResponse if the photo is frozen,
    raises HTTPException(404) if not found,
    otherwise returns PhotoNavContext.
    """
    # Step 1: resolve from full index (needed for frozen check)
    all_index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(all_index.keys()))

    # Step 2: frozen redirect
    if full_hash:
        frozen_set = is_frozen(full_hash)
        if frozen_set:
            return RedirectResponse(
                url=str(request.url_for(
                    'frozen_photo_detail',
                    set_name=frozen_set,
                    content_hash=full_hash[:8],
                )),
                status_code=302,
            )

    # Step 3: resolve from filtered hashes
    full_hash = find_hash_by_prefix(content_hash, filtered_hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    # Step 4: navigation
    try:
        idx = filtered_hashes.index(full_hash)
    except ValueError:
        raise HTTPException(status_code=404, detail='Photo not in current filter')

    total = len(filtered_hashes)
    prev_url = (
        str(request.url_for(route_name, content_hash=filtered_hashes[idx - 1][:8]))
        + filter_suffix
    ) if idx > 0 else None
    next_url = (
        str(request.url_for(route_name, content_hash=filtered_hashes[idx + 1][:8]))
        + filter_suffix
    ) if idx < total - 1 else None

    return PhotoNavContext(
        full_hash=full_hash,
        idx=idx,
        total=total,
        prev_url=prev_url,
        next_url=next_url,
        all_index=all_index,
    )
```

### New: `tests/test_nav_helper.py`

Unit tests for `resolve_photo_nav` in isolation (mock `load_photo_index`, `is_frozen`, `find_hash_by_prefix`):

- `test_resolve_returns_context_for_valid_hash` — happy path
- `test_resolve_raises_404_for_unknown_hash` — not in filtered hashes
- `test_resolve_returns_redirect_for_frozen_hash` — frozen → RedirectResponse
- `test_resolve_prev_next_urls` — first/middle/last positions
- `test_resolve_includes_all_index` — `all_index` is populated

## Scope boundaries

- **In scope**: new `nav.py` file + unit tests
- **Out of scope**: refactoring the handlers (tasks 055, 056), `frozen.py` changes, template changes
- **Do not** modify `labeling.py` — that happens in tasks 055/056
