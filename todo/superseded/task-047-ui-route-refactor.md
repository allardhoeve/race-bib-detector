# Task 047: Extract shared UI route logic + add test coverage

Independent of other open tasks. No prerequisites.

## Goal

Eliminate the copy-paste duplication across `bib_photo()`, `face_photo()`, and `association_photo()` by extracting the shared hash-resolution + navigation pattern into a reusable helper. Add integration tests for all untested UI route handlers.

## Background

`benchmarking/routes/ui/labeling.py` (364 lines) contains three 80+ line handlers that repeat the same steps:
1. Resolve hash prefix → check if frozen → redirect or 404
2. Find position in filtered list → build prev/next URLs
3. Load handler-specific GT → assemble template context → render

Steps 1–2 are identical across all three. The frozen viewer (`ui/frozen.py`) also duplicates the navigation pattern. Meanwhile, none of these handlers have meaningful test coverage — only the three `*_index()` redirect endpoints are tested.

| File | Function | Lines | Tests |
|------|----------|-------|-------|
| `ui/labeling.py` | `bib_photo()` | 84 | 0 |
| `ui/labeling.py` | `face_photo()` | 84 | 0 |
| `ui/labeling.py` | `association_photo()` | 87 | 0 |
| `ui/benchmark.py` | `benchmark_inspect()` | 58 | 0 |
| `ui/frozen.py` | `frozen_photo_detail()` | 48 | 1 |

## Context

- `benchmarking/routes/ui/labeling.py` — the three handlers to refactor
- `benchmarking/label_utils.py` — `find_hash_by_prefix()`, `find_next_unlabeled_url()`, `get_filtered_hashes()`, `get_filtered_face_hashes()`
- `benchmarking/frozen_check.py` — `is_frozen()`
- `benchmarking/photo_index.py` — `load_photo_index()`
- `benchmarking/services/completion_service.py` — `workflow_context_for()`, `get_link_ready_hashes()`, `get_unlinked_hashes()`, `get_underlinked_hashes()`
- `tests/test_web_app.py` — existing test patterns: `TestClient(create_app(), follow_redirects=False)`, monkeypatch GT paths to `tmp_path`
- `tests/test_frozen_check.py` — frozen fixture pattern with explicit GT construction
- `tests/test_link_api.py` — link_client fixture with bib+face GT

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Helper location | New file `benchmarking/routes/ui/nav.py` — keeps it close to the routes that use it, avoids bloating `label_utils.py` with HTTP-aware code |
| Return type | `PhotoNavContext | RedirectResponse` — caller checks `isinstance` and returns redirect early |
| filter_suffix | Passed by caller as a string — bibs/faces always pass `?filter={type}`, associations pass empty when `all` |
| all_index on context | Include `all_index: dict` on `PhotoNavContext` — `bib_photo` and `face_photo` need it for `find_next_unlabeled_url()` |
| frozen.py | Leave as-is — it's the frozen viewer itself (no frozen redirect), different URL params (`set_name`), and only 48 lines |
| benchmark_inspect() | Tests only, no refactor — the JSON serialization is a separate concern |

## Changes

### New: `benchmarking/routes/ui/nav.py`

```python
from dataclasses import dataclass

@dataclass
class PhotoNavContext:
    """Resolved hash + navigation state for a photo detail page."""
    full_hash: str
    idx: int            # 0-based position in filtered list
    total: int
    prev_url: str | None
    next_url: str | None
    all_index: dict     # full photo index (for next-unlabeled lookups)

def resolve_photo_nav(
    content_hash: str,
    filtered_hashes: list[str],
    request: Request,
    route_name: str,
    filter_suffix: str = '',
) -> PhotoNavContext | RedirectResponse:
    """Resolve hash, check frozen, build navigation.

    Returns RedirectResponse if the photo is frozen,
    raises HTTPException(404) if not found,
    otherwise returns PhotoNavContext.
    """
```

Logic moved here:
- Load `load_photo_index()` → `find_hash_by_prefix()` against full index
- `is_frozen()` → `RedirectResponse` to `frozen_photo_detail`
- `find_hash_by_prefix()` against filtered hashes → 404
- Index lookup + prev/next URL building

### Modified: `benchmarking/routes/ui/labeling.py`

Each handler becomes:

```python
@ui_labeling_router.get('/bibs/{content_hash}')
async def bib_photo(content_hash, request, filter_type=Query(...)):
    hashes = get_filtered_hashes(filter_type)
    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    nav = resolve_photo_nav(content_hash, hashes, request, 'bib_photo', f'?filter={filter_type}')
    if isinstance(nav, RedirectResponse):
        return nav

    # Handler-specific: load bib GT, metadata, next-unlabeled, render template
    ...
```

Expected: each handler shrinks from ~84 → ~35 lines. File total from 364 → ~230.

### New: `tests/test_ui_routes.py`

Fixtures:
- `labeling_client` — monkeypatch paths, photo index with 3 hashes, bib+face GT for 1 labeled photo
- `link_client` — extends with link GT for association tests
- `frozen_client` — extends with a frozen snapshot, for redirect tests
- `benchmark_client` — monkeypatches `get_run()` and `list_runs()` to return a minimal run

Test classes:

```
TestBibPhoto
  test_renders_200                     # happy path: labeled photo, check key HTML content
  test_404_unknown_hash                # bad prefix → 404
  test_frozen_redirect                 # frozen hash → 302 to /frozen/...
  test_empty_filter_shows_empty_page   # no hashes match filter → empty.html

TestFacePhoto
  test_renders_200
  test_404_unknown_hash
  test_frozen_redirect

TestAssociationPhoto
  test_renders_200
  test_404_unknown_hash
  test_frozen_redirect

TestBenchmarkInspect
  test_renders_200
  test_404_missing_run
  test_filter_narrows_results

TestFrozenPhotoDetail
  test_renders_200
  test_404_unknown_hash
```

## Scope boundaries

- **In scope**: extract `nav.py` helper, refactor 3 labeling handlers, add tests for all 5 untested UI handlers
- **Out of scope**: frozen.py refactoring, benchmark_inspect() refactoring, template changes, API route changes
- **Do not** change any external behaviour — all URLs, redirects, and template contexts stay the same
