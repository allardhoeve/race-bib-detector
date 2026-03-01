# Task 052: Enrich inspect route with GT + prediction box data

Depends on task-049 and task-050. Independent of task-051.

## Goal

Update the benchmark inspect route and `photo_results_json` blob to include bib/face prediction and GT box coordinates, so the inspect page JavaScript can render overlays.

## Background

After tasks 049-050, `PhotoResult` carries `pred_bib_boxes`, `pred_face_boxes`, `gt_bib_boxes`, and `gt_face_boxes`. The inspect route currently serialises only a subset of `PhotoResult` fields into the JSON blob passed to the browser. This task adds the box data to that blob in a format suitable for canvas rendering.

## Context

- `benchmarking/routes/ui/benchmark.py:33` — `benchmark_inspect()` route handler
- `benchmarking/routes/ui/benchmark.py` — builds `photo_results_json` from filtered results
- `benchmarking/templates/benchmark_inspect.html` — receives `photo_results_json` as `window.PAGE_DATA.photoResults`
- `benchmarking/ground_truth.py:76` — `BibBox` fields: x, y, w, h, number, scope
- `benchmarking/ground_truth.py:200` — `FaceBox` fields: x, y, w, h, scope, identity, tags, (cluster_id if task-051 done)

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Serialisation format | Use `model_dump()` on each box — Pydantic handles it. JS receives plain objects with `x, y, w, h, number, scope, ...` |
| Filter GT boxes? | No — send all GT boxes; let JS colour-code by scope |
| Include `None` box lists? | Omit from JSON when `None` (old runs). JS checks for presence before rendering |
| Link data | Include link GT if available: `gt_links: [{bib_index, face_index}, ...]` per photo |
| Performance | 250 photos × ~10 boxes × ~50 bytes each ≈ 125KB JSON — negligible |

## Changes

### Modified: `benchmarking/routes/ui/benchmark.py`

Update the serialisation of `photo_results_json` to include box data. Currently the route builds the JSON list manually or via `model_dump()`. Ensure the new fields are included:

```python
# When building photo_results_json:
result_data = result.model_dump(
    include={
        "content_hash", "expected_bibs", "detected_bibs",
        "tp", "fp", "fn", "status", "detection_time_ms",
        "tags", "artifact_paths", "preprocess_metadata",
        "pred_bib_boxes", "pred_face_boxes",
        "gt_bib_boxes", "gt_face_boxes",
    },
    exclude_none=True,
)
```

Using `exclude_none=True` means old runs (where box fields are `None`) produce the same JSON as before — no breaking change for existing JS.

Optionally load link GT and attach per-photo:

```python
from benchmarking.ground_truth import load_link_ground_truth
link_gt = load_link_ground_truth()
# Per photo:
links = link_gt.get_links(result.content_hash) if link_gt else []
result_data["gt_links"] = [link.model_dump() for link in links]
```

### Modified: `benchmarking/templates/benchmark_inspect.html`

No template changes in this task — only the JSON blob content changes. The JS rendering is task-053.

But verify that the existing detail panel still works by checking that the JS only accesses fields it knows about (it does — it reads specific keys, not iterating all keys).

## Tests

Extend `tests/benchmarking/test_benchmark_routes.py` (or the appropriate route test file):

- `test_inspect_json_includes_pred_bib_boxes()` — create a run with box data, GET inspect page, parse `photo_results_json` from response, verify `pred_bib_boxes` is present
- `test_inspect_json_excludes_none_boxes()` — old-style run without box data → fields absent from JSON
- `test_inspect_json_includes_gt_links()` — verify `gt_links` array in JSON

## Verification

```bash
venv/bin/python -m pytest tests/benchmarking/ -v -k inspect

# Manual: run benchmark, open inspect page, check browser DevTools console:
# JSON.parse(document.getElementById('photo-results-data').textContent)[0]
# → should show pred_bib_boxes, gt_bib_boxes arrays
```

## Acceptance criteria

- [x] All existing tests still pass (`venv/bin/python -m pytest`)
- [x] New tests pass
- [x] Inspect page JSON includes `pred_bib_boxes` and `gt_bib_boxes` when present
- [x] Inspect page JSON includes `pred_face_boxes` and `gt_face_boxes` when present
- [x] Old runs (without box data) still render correctly — no JS errors
- [x] Link GT data included per photo when available

## Scope boundaries

- **In scope**: route JSON enrichment, backward-compatible serialisation
- **Out of scope**: canvas rendering (task-053), face clustering (task-051)
- **Do not** change `PhotoResult` fields (task-049), detection logic (task-050), or template HTML/JS
