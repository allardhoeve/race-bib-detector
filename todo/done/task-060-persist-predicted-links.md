# Task 060: Persist predicted links in PhotoResult and show on overlay

Independent of task-066.

## Goal

Store the predicted bib↔face links from `predict_links()` on each `PhotoResult` so they are saved in `run.json`, passed to the inspect page, and drawn on the canvas overlay. This is the missing piece for the bib number → face → all photos retrieval pipeline.

## Background

Task-031 wired `predict_links()` into the benchmark runner for **scoring** (LinkScorecard), but the per-photo predicted pairs are discarded after scoring. The inspect overlay currently only draws GT links (amber dashed lines). To debug and improve the autolink algorithm we need to see predicted links too, and eventually the production pipeline needs these pairs for photo retrieval.

## Context

- `benchmarking/runner.py` — `PhotoResult` model (line ~72); `_run_detection_loop` calls `predict_links()` at line ~588 but discards the result after scoring
- `faces/autolink.py` — `predict_links()` returns `AutolinkResult` with `.pairs: list[tuple[BibBox, FaceBox]]` (box object references, not indices)
- `benchmarking/ground_truth.py` — `BibFaceLink(bib_index, face_index)` is the index-based pair format used for GT links
- `benchmarking/routes/ui/benchmark.py` — inspect route builds `photo_results_json`, already includes `gt_links`
- `benchmarking/static/inspect_overlay.js` — `_drawLinks()` draws GT links; needs a second call for predicted links
- `benchmarking/templates/benchmark_inspect.html` — overlay legend already has a GT link entry; needs a predicted link entry

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Storage format for predicted links | `list[BibFaceLink]` — same `{bib_index, face_index}` format as GT links, reusing existing model |
| How to convert box refs to indices | Match `autolink.pairs` back to `pred_bib_boxes` / `pred_face_boxes` by identity (same object) or by coordinate equality |
| Overlay colour for predicted links | Distinct from GT amber (#f59e0b) — use cyan/teal (#06b6d4) solid line to contrast with amber dashed GT lines |

## Changes

### Modified: `benchmarking/runner.py`

1. Add `pred_links: list[BibFaceLink] | None = None` field to `PhotoResult`.
2. After `autolink = predict_links(...)` (line ~588), convert `autolink.pairs` to index-based `BibFaceLink` list and store on `photo_result.pred_links`.

```python
# Convert box-ref pairs to index pairs
pred_link_list = []
for bib_box, face_box in autolink.pairs:
    try:
        bi = pred_bib_boxes.index(bib_box)
        fi = pred_face_boxes.index(face_box)
        pred_link_list.append(BibFaceLink(bib_index=bi, face_index=fi))
    except ValueError:
        pass  # box not in list (shouldn't happen)
photo_result.pred_links = pred_link_list
```

### Modified: `benchmarking/routes/ui/benchmark.py`

Add `'pred_links'` to the `include` set in `model_dump()` so predicted links are serialised to the inspect page JSON.

### Modified: `benchmarking/static/inspect_overlay.js`

1. In `draw()`, add a block after GT links to draw predicted links using `data.pred_links` with `pred_bib_boxes` / `pred_face_boxes` as the box arrays.
2. Use solid cyan (#06b6d4) line to distinguish from dashed amber GT links.
3. Add `showPredLinks` option (default true) or reuse the existing `showLinks` + `showPred` combination.

### Modified: `benchmarking/templates/benchmark_inspect.html`

Add a predicted link swatch to the overlay legend:
```html
<span class="legend-item"><span class="legend-swatch solid" style="background:#06b6d4;"></span>Pred link</span>
```

## Tests

Extend `tests/test_runner.py`:

- [ ] `test_photo_result_has_pred_links()` — run detection on a photo with visible bib+face; verify `pred_links` is a list of `BibFaceLink` with valid indices into `pred_bib_boxes` / `pred_face_boxes`.

Extend `tests/test_runner_models.py`:

- [ ] `test_pred_links_serialization()` — verify `PhotoResult` with `pred_links` round-trips through `model_dump()` / `model_validate()`.

## Verification

```bash
venv/bin/python -m pytest tests/test_runner.py tests/test_runner_models.py -v
```

Manual: open inspect page, verify predicted link lines (cyan solid) appear alongside GT link lines (amber dashed).

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `PhotoResult.pred_links` field exists and is populated by the runner
- [ ] `run.json` contains `pred_links` arrays per photo
- [ ] Inspect overlay draws predicted links in a visually distinct colour from GT links
- [ ] Legend includes predicted link entry

## Scope boundaries

- **In scope**: persisting predicted links, overlay visualisation, legend update
- **Out of scope**: changing the autolink algorithm itself, production retrieval pipeline, link scoring changes
- **Do not** change `predict_links()` or `score_links()` signatures
