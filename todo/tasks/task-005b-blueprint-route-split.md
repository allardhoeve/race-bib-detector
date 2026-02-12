# Task 005b: Split routes into domain-based Blueprints

Part 2 of 3 — see also [005a](task-005a-extract-templates-and-js.md), [005c](task-005c-extract-helpers-cleanup.md).
Depends on 005a being complete.

## Goal

Split the monolithic `create_app()` into Flask Blueprints grouped by domain.
`web_app.py` shrinks to an app factory that registers blueprints.
Pure refactoring — no behavior changes.

## Blueprint layout

| Module | Blueprint name | Routes | ~Lines |
|--------|---------------|--------|--------|
| `routes_bib.py` | `bib` | `/labels/`, `/labels/<hash>`, `/api/labels`, `/api/bib_boxes/<hash>` | ~120 |
| `routes_face.py` | `face` | `/faces/`, `/faces/labels/`, `/faces/labels/<hash>`, `/api/face_labels`, `/api/face_boxes/<hash>`, `/api/identities`, `/api/rename_identity`, `/api/face_identity_suggestions/<hash>`, `/api/face_crop/<hash>/<idx>` | ~250 |
| `routes_benchmark.py` | `benchmark` | `/benchmark/`, `/benchmark/<run_id>/`, `/artifact/<run_id>/<hash>/<type>` | ~100 |
| `web_app.py` (remains) | app factory | `/` redirect, `/photo/<hash>`, `/test/labeling`, blueprint registration, `main()` | ~80 |

### Domain-based rationale

Grouping pages + their APIs together (rather than separating pages vs API layer)
means you read one file to understand one feature. This also positions well for
step 5 (bib-face linking), which can get its own module.

### Shared state: `_embedding_index_cache`

Currently a local variable inside `create_app()` (line 2240), used only by
`face_identity_suggestions`. Move to a module-level dict in `routes_face.py`.

### Blueprint registration pattern

```python
# web_app.py
from benchmarking.routes_bib import bib_bp
from benchmarking.routes_face import face_bp
from benchmarking.routes_benchmark import benchmark_bp

def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / 'templates'),
        static_folder=str(Path(__file__).parent / 'static'),
    )
    app.register_blueprint(bib_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(benchmark_bp)

    @app.route('/')
    def index():
        return redirect(url_for('bib.labels_index'))

    @app.route('/photo/<content_hash>')
    def serve_photo(content_hash):
        ...

    return app
```

### url_for name changes

Blueprint registration changes endpoint names from `'labels_index'` to
`'bib.labels_index'`. This affects:
- Python `url_for()` calls in route handlers
- Jinja2 `{{ url_for(...) }}` in templates
- `PAGE_DATA` blocks in templates that pass URLs to static JS

Audit all `url_for()` calls. The templates (from 005a) and routes must be
updated together.

### Migration steps

1. Create `routes_bib.py` with `bib_bp = Blueprint('bib', __name__)`. Move
   bib routes + their handler bodies. Update `url_for` calls.
2. Run tests. Fix any endpoint name mismatches.
3. Repeat for `routes_face.py`, then `routes_benchmark.py`.
4. Slim down `create_app()` to app factory + common routes.
5. Run full test suite.

## Test strategy

- Tests import `from benchmarking.web_app import create_app` — this still works
  since `create_app` stays in `web_app.py`.
- Tests monkeypatch at source module level (`benchmarking.ground_truth.*`,
  `benchmarking.identities.*`, etc.) — these paths don't change.
- Run `pytest tests/test_web_app.py` after each blueprint migration.
- Run full `pytest` at the end.

## Scope boundaries

- **In scope**: route splitting, blueprint registration, `url_for` updates.
- **Out of scope**: new features, renaming URL paths, changing API contracts.
