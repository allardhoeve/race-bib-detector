# Task 005c: Static serving cleanup

Part 3 of 3 — 005a and 005b are both done (in `todo/done/`).

## Current state

- `benchmarking/label_utils.py` exists with all helper functions — **section 1 is done**.
- Route files (`routes_bib.py`, `routes_face.py`, `routes_benchmark.py`) already import from `label_utils`.
- `web_app.py` is 132 lines — just the app factory + shared routes.
- `serve_static` custom route still exists; templates still reference `url_for('serve_static', ...)`.
- `_json_default` does not exist in the codebase — section 3 is moot.

## Goal

Replace the custom `serve_static` route with Flask's built-in static serving.
Pure cleanup — no behavior changes, no new features.

## Changes

### 1. Add `static_folder` to Flask constructor (`web_app.py` line 40)

```python
# Before
app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / 'templates'),
)

# After
app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / 'templates'),
    static_folder=str(Path(__file__).parent / 'static'),
)
```

### 2. Delete `serve_static` route (`web_app.py` lines 79–83)

```python
# Delete this entire route:
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static assets (JS, CSS, HTML)."""
    static_dir = Path(__file__).parent / 'static'
    return send_from_directory(static_dir, filename)
```

### 3. Replace `test_labeling` route with redirect (`web_app.py` lines 85–89)

```python
# Before
@app.route('/test/labeling')
def test_labeling():
    """Serve the browser integration test page."""
    static_dir = Path(__file__).parent / 'static'
    return send_from_directory(static_dir, 'test_labeling.html')

# After
@app.route('/test/labeling')
def test_labeling():
    """Redirect to the browser integration test page."""
    return redirect(url_for('static', filename='test_labeling.html'))
```

### 4. Remove `send_from_directory` from imports (`web_app.py` line 20)

```python
# Before
from flask import Flask, render_template, send_file, send_from_directory, redirect, url_for

# After
from flask import Flask, render_template, send_file, redirect, url_for
```

### 5. Update templates — 5 occurrences of `url_for('serve_static', ...)`

| File | Line | Before | After |
|------|------|--------|-------|
| `templates/labeling.html` | 236 | `url_for('serve_static', filename='labeling.js')` | `url_for('static', filename='labeling.js')` |
| `templates/labeling.html` | 248 | `url_for('serve_static', filename='bib_labeling_ui.js')` | `url_for('static', filename='bib_labeling_ui.js')` |
| `templates/face_labeling.html` | 298 | `url_for('serve_static', filename='labeling.js')` | `url_for('static', filename='labeling.js')` |
| `templates/face_labeling.html` | 310 | `url_for('serve_static', filename='face_labeling_ui.js')` | `url_for('static', filename='face_labeling_ui.js')` |
| `templates/benchmark_inspect.html` | 231 | `url_for('serve_static', filename='benchmark_inspect.js')` | `url_for('static', filename='benchmark_inspect.js')` |

## Test strategy

- Run `pytest tests/test_web_app.py` — no tests reference `serve_static`, but run to verify nothing broke.
- Run full `pytest` at the end.
- Manually load `/labels/`, `/faces/labels/`, `/benchmark/` in browser — verify JS loads correctly.
- Navigate to `/test/labeling` — verify redirect works.

## Scope boundaries

- **In scope**: static serving switch, `send_from_directory` cleanup.
- **Out of scope**: new features, CSS changes, API changes, route renames.
