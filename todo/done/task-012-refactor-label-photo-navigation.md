# Task 012: Deduplicate label_photo / face_label_photo navigation logic

Small focused refactor. Independent of all other pending tasks.

## Goal

`label_photo()` (`routes_bib.py:36–101`) and `face_label_photo()` (`routes_face.py:56–123`)
are 65–67 lines each with near-identical structure. In particular, the "find next unlabeled"
loop (routes_bib.py:68–79, routes_face.py:90–101) is copy-pasted verbatim except for the
GT loader and labeled-check. Extract it into `label_utils.py`.

## Current duplication

`routes_bib.py:68–79`:
```python
all_hashes_sorted = sorted(load_photo_index().keys())
next_unlabeled_url = None
try:
    all_idx = all_hashes_sorted.index(full_hash)
    for h in all_hashes_sorted[all_idx + 1:]:
        lbl = bib_gt.get_photo(h)
        if not lbl or not lbl.labeled:
            next_unlabeled_url = url_for('bib.label_photo', content_hash=h[:8], filter=filter_type)
            break
except ValueError:
    pass
```

`routes_face.py:90–101`: identical structure, using `face_gt`, `is_face_labeled(fl)`,
and `'face.face_label_photo'` endpoint.

## Changes

### 1. Add to `benchmarking/label_utils.py`

```python
from typing import Callable

def find_next_unlabeled_url(
    full_hash: str,
    all_hashes_sorted: list[str],
    is_labeled_fn: Callable[[str], bool],
    endpoint: str,
    filter_type: str,
) -> str | None:
    """Return url_for the next unlabeled photo after full_hash, or None."""
    from flask import url_for
    try:
        all_idx = all_hashes_sorted.index(full_hash)
        for h in all_hashes_sorted[all_idx + 1:]:
            if not is_labeled_fn(h):
                return url_for(endpoint, content_hash=h[:8], filter=filter_type)
    except ValueError:
        pass
    return None
```

### 2. Update `routes_bib.py:68–79`

Replace the hand-written loop with:
```python
all_hashes_sorted = sorted(load_photo_index().keys())
next_unlabeled_url = find_next_unlabeled_url(
    full_hash,
    all_hashes_sorted,
    is_labeled_fn=lambda h: bool(bib_gt.get_photo(h) and bib_gt.get_photo(h).labeled),
    endpoint='bib.label_photo',
    filter_type=filter_type,
)
```

Or, to avoid the double `get_photo()` call:
```python
def _bib_is_labeled(h: str) -> bool:
    lbl = bib_gt.get_photo(h)
    return bool(lbl and lbl.labeled)

next_unlabeled_url = find_next_unlabeled_url(
    full_hash, all_hashes_sorted, _bib_is_labeled, 'bib.label_photo', filter_type
)
```

Also add `find_next_unlabeled_url` to the import from `label_utils`.

### 3. Update `routes_face.py:90–101`

```python
all_hashes_sorted = sorted(load_photo_index().keys())
next_unlabeled_url = find_next_unlabeled_url(
    full_hash,
    all_hashes_sorted,
    is_labeled_fn=lambda h: is_face_labeled(face_gt.get_photo(h)) if face_gt.get_photo(h) else False,
    endpoint='face.face_label_photo',
    filter_type=filter_type,
)
```

Also add `find_next_unlabeled_url` to the import.

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md).

- Run `pytest tests/test_web_app.py` — navigation tests should pass unchanged.
- Manual: open `/labels/` and `/faces/labels/`, navigate photos, verify "Next unlabeled"
  button appears and links to the correct photo.

## Scope boundaries

- **In scope**: extracting the next-unlabeled loop; updating both route handlers; updating
  `label_utils.py`.
- **Out of scope**: merging the full `label_photo` / `face_label_photo` bodies (different GT,
  template variables, and split logic make this more invasive and less clear).
- **Do not** change API endpoints, template variables, or test fixtures.
