# Task 025: Replace Flask with FastAPI

Depends on task-019, task-020, task-021, task-024. Supersedes task-023.

## Goal

Swap the Flask app for a FastAPI app. Replace `Blueprint` with `APIRouter`,
update all route decorators and request/response patterns, and mount Jinja2
templates + static files via Starlette. The result is an identical-looking app
from the browser's perspective, with automatic OpenAPI docs at `/docs/`.

Task-023 (Flasgger/Swagger) is superseded by this task — FastAPI generates
OpenAPI 3.1 from type hints with zero extra annotation work.

## Background

Flask requires manual `request.get_json()`, `jsonify()`, and `abort()`. FastAPI
replaces these with Python type hints: a `dict` return value is auto-serialised,
a Pydantic body parameter is auto-validated, and raising `HTTPException` produces
a JSON error response.

The app has ~20 API endpoints and ~10 HTML/media endpoints. All live in three
route files. The service layer (task-021) has already moved business logic out of
the handlers, so the handlers themselves are thin: validate → call service →
return. FastAPI makes this pattern explicit.

FastAPI is built on Starlette, which handles Jinja2 templates, static file
serving, and `StreamingResponse` / `FileResponse` natively.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| ASGI server | `uvicorn` — standard pairing with FastAPI |
| Templates | `starlette.templating.Jinja2Templates` — same template files, no changes to HTML/JS |
| Static files | `app.mount("/static", StaticFiles(directory="benchmarking/static"), name="static")` |
| Blueprint → APIRouter | One `APIRouter` per existing blueprint; same URL prefixes |
| `url_for` in templates | Starlette's `request.url_for("route_name")` — pass `request` to all templates |
| `send_file` / `send_from_directory` | `FileResponse(path)` or `StreamingResponse(buf, media_type=...)` |
| `abort(404)` | `raise HTTPException(status_code=404)` |
| `request.get_json()` | Pydantic body parameters (task-026) or `body: dict = Body(...)` as interim |
| Error responses | FastAPI's default 422 for validation errors; keep explicit 400/404 as `HTTPException` |
| Dependency injection | Use `Depends()` for `get_photo_index()`, `get_face_gt()` etc. if desired — optional, can be deferred |
| Keep `run.py` / CLI entry? | Yes — update to call `uvicorn.run("benchmarking.app:app", ...)` |

## Changes: `benchmarking/app.py` (replaces `web_app.py`)

```python
"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from pathlib import Path

from benchmarking.routes.bib import bib_router
from benchmarking.routes.face import face_router
from benchmarking.routes.identities import identities_router
from benchmarking.routes.benchmark import benchmark_router

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(
        title="BNR Benchmark",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )

    app.include_router(bib_router)
    app.include_router(face_router)
    app.include_router(identities_router)
    app.include_router(benchmark_router)

    @app.get("/", include_in_schema=False)
    async def index(request: Request):
        return TEMPLATES.TemplateResponse("index.html", {"request": request, ...})

    return app


app = create_app()
```

Note: `web_app.py` stays in place as a shim that imports `create_app` from
`app.py` until all callers are updated, then it is deleted.

## Changes: route files — Flask → FastAPI patterns

### Blueprint → APIRouter

**Before (Flask):**
```python
from flask import Blueprint
bib_bp = Blueprint('bib', __name__)

@bib_bp.route('/api/bibs/<content_hash>')
def get_bib_boxes(content_hash: str):
    ...
    return jsonify(result)
```

**After (FastAPI):**
```python
from fastapi import APIRouter
bib_router = APIRouter()

@bib_router.get('/api/bibs/{content_hash}')
async def get_bib_boxes(content_hash: str):
    ...
    return result  # dict is auto-serialised
```

Key syntax differences:
- URL params: `:name` → `{name}`
- Methods split: `methods=['GET', 'POST']` → separate `@router.get()` / `@router.post()`
- `async def` preferred (not required for non-async handlers)

### Request bodies

**Before (Flask):**
```python
data = request.get_json()
content_hash = data.get('content_hash')
if not content_hash:
    return jsonify({'error': 'Missing content_hash'}), 400
```

**After (FastAPI, interim — full schemas in task-026):**
```python
from fastapi import Body

async def save_bib_boxes(content_hash: str, body: dict = Body(...)):
    content_hash = body.get('content_hash') or content_hash
    ...
```

Or, after task-026 lands, use a typed Pydantic body model — the 400 validation
is then automatic.

### 404 / error responses

**Before (Flask):**
```python
return jsonify({'error': 'Photo not found'}), 404
# or:
abort(404)
```

**After (FastAPI):**
```python
from fastapi import HTTPException
raise HTTPException(status_code=404, detail='Photo not found')
```

### Template responses

**Before (Flask):**
```python
from flask import render_template
return render_template('face_labeling.html', content_hash=..., ...)
```

**After (FastAPI):**
```python
from fastapi import Request
from starlette.responses import HTMLResponse

async def face_label_photo(request: Request, content_hash: str):
    return TEMPLATES.TemplateResponse(
        'face_labeling.html',
        {'request': request, 'content_hash': ..., ...}
    )
```

Note: every template response must include `'request': request` in the context.

### url_for in templates

Jinja2 templates that call `url_for('blueprint.view_name', ...)` must be updated.
Starlette's `url_for` is available in templates via `request.url_for('route_name')`.
Route names in FastAPI are the function names (no blueprint prefix).

**Before (template):**
```jinja2
{{ url_for('face.face_label_photo', content_hash=h[:8]) }}
```

**After (template):**
```jinja2
{{ request.url_for('face_label_photo', content_hash=h[:8]) }}
```

This is a mechanical find-and-replace across all `.html` templates. Do it after
confirming all route function names.

### Binary / file responses

**Before (Flask):**
```python
return send_file(buf, mimetype='image/jpeg')
```

**After (FastAPI):**
```python
from starlette.responses import StreamingResponse
return StreamingResponse(buf, media_type='image/jpeg')
```

For a file on disk:
```python
from starlette.responses import FileResponse
return FileResponse(path, media_type='image/jpeg')
```

### Redirects

**Before (Flask):**
```python
return redirect(url_for('face.face_labels_index'))
```

**After (FastAPI):**
```python
from starlette.responses import RedirectResponse
return RedirectResponse(url=request.url_for('face_labels_index'), status_code=302)
```

## Changes: `run.py` / entry point

```python
import uvicorn
from benchmarking.app import app

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=30002, reload=True)
```

## Changes: `requirements.txt` / `pyproject.toml`

```
# Add:
fastapi>=0.110
uvicorn[standard]>=0.29
python-multipart>=0.0.9   # required for form data if any

# Remove (after migration is complete):
flask
```

Keep `flask` in requirements until all route files are migrated so that the old
`web_app.py` shim remains importable during the transition.

## Migration order

Migrate one router at a time, keeping the Flask app runnable in parallel if possible.
If a parallel run is not practical, migrate all routers in one branch and test
end-to-end before merging.

Recommended order:
1. Create `benchmarking/app.py` skeleton with FastAPI instance (no routes yet).
2. Migrate `routes_bib.py` → FastAPI router; verify bib labeling UI still works.
3. Migrate `routes_face.py` → FastAPI router; verify face labeling UI still works.
4. Migrate `routes_identities.py` → FastAPI router.
5. Migrate `routes_benchmark.py` → FastAPI router.
6. Update all Jinja2 templates for `request.url_for(...)`.
7. Delete `web_app.py` and the Flask shim.
8. Update `run.py` to use uvicorn.
9. Remove Flask from requirements.

## Tests

The existing Flask test client tests (`flask.testing.FlaskClient`) must be
replaced with FastAPI's `TestClient` from `starlette.testclient`:

```python
from starlette.testclient import TestClient
from benchmarking.app import app

client = TestClient(app)
response = client.get('/api/bibs/abc123')
```

The `TestClient` API is intentionally compatible with `requests`, so most test
bodies change only in the import and client construction.

## Scope boundaries

- **In scope**: `app.py`, all `routes_*.py`, `run.py`, `requirements.txt`,
  Jinja2 templates (url_for updates only), test client imports.
- **Out of scope**: Template HTML/CSS/JS logic, service layer (task-021), URL
  paths (task-019/020), request/response schema definitions (task-026).
- **Do not** change the URLs — those are owned by task-019 and task-020.
- **Do not** add Flasgger — FastAPI generates OpenAPI automatically; task-023
  is superseded.
- **Do not** refactor templates beyond the `url_for` mechanical replacement.
