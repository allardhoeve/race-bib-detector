# Task 005c: Extract helpers and static-serving cleanup

Part 3 of 3 — see also [005a](../done/task-005a-extract-templates-and-js.md), [005b](task-005b-blueprint-route-split.md).
Depends on 005b being complete.

## Goal

Final cleanup: move utility functions out of `web_app.py` into a small module,
and switch from the custom `/static/` route to Flask's built-in static serving.

## 1. Extract helpers to `benchmarking/label_utils.py`

Move these module-level functions out of `web_app.py`:

| Function | Used by |
|----------|---------|
| `get_filtered_hashes(filter_type)` | `routes_bib.py` |
| `get_filtered_face_hashes(filter_type)` | `routes_face.py` |
| `is_face_labeled(label)` | `get_filtered_face_hashes`, `routes_face.py` |
| `find_hash_by_prefix(prefix, hashes)` | all route modules |
| `filter_results(results, filter_type)` | `routes_benchmark.py` |

These have no Flask dependencies — they operate on ground truth data only.
Import them from `benchmarking.label_utils` in each route module.

## 2. Switch to Flask built-in static serving

Currently there's a custom route:
```python
@app.route('/static/<path:filename>')
def serve_static(filename):
    static_dir = Path(__file__).parent / 'static'
    return send_from_directory(static_dir, filename)
```

Replace with Flask's built-in `static_folder` parameter (already set in 005b):
```python
app = Flask(
    __name__,
    static_folder=str(Path(__file__).parent / 'static'),
)
```

Then:
- Delete the `serve_static` route and `serve_from_directory` import.
- Delete the `test_labeling` route (serve via static or a simple redirect).
- Update any `url_for('serve_static', filename=...)` → `url_for('static', filename=...)`.
- Verify static assets load correctly (labeling.js, bib_labeling_ui.js,
  face_labeling_ui.js, benchmark_inspect.js, test_labeling.html).

## 3. Clean up `_json_default`

Line 1876: `_json_default` helper. Check if it's still used after the
refactoring. If yes, move to `label_utils.py`. If not, delete.

## Final state

After all three tasks, the file layout should be:

```
benchmarking/
  web_app.py           (~80 lines — app factory, common routes, main)
  routes_bib.py        (~120 lines)
  routes_face.py       (~250 lines)
  routes_benchmark.py  (~100 lines)
  label_utils.py       (~80 lines)
  templates/
    base.html
    empty.html
    labels_home.html
    labeling.html
    face_labeling.html
    benchmark_list.html
    benchmark_inspect.html
  static/
    labeling.js              (existing — LabelingCore)
    bib_labeling_ui.js       (new — bib LabelingUI)
    face_labeling_ui.js      (new — face LabelingUI)
    benchmark_inspect.js     (new — benchmark inspect UI)
    test_labeling.html       (existing)
```

## Test strategy

- Run `pytest tests/test_web_app.py` after each change.
- Run full `pytest` at the end.
- Manually verify static assets load in browser.

## Scope boundaries

- **In scope**: helper extraction, static serving cleanup, dead code removal.
- **Out of scope**: new features, CSS changes, API changes.
