# API Design

This document captures the design principles, current endpoint inventory, and decisions for the benchmarking web app's HTTP API.

Project-wide conventions live in `STANDARDS.md`.
Benchmark system design lives in `BENCHMARK_DESIGN.md`.

---

## Principles

### URL structure

Endpoints follow two shapes:

```
GET  /api/<resource>            →  list all (bulk read)
GET  /api/<resource>/<hash>     →  single item
PUT  /api/<resource>/<hash>     →  save / replace single item
POST /api/<action>              →  commands that don't fit CRUD (freeze, label flags, etc.)
```

Routes are registered on Flask blueprints (`bib_bp`, `face_bp`, `benchmark_bp`) but share a flat `/api/` namespace — there is no URL prefix per blueprint.

### Bulk reads: list-all over filtered queries

For bulk reads the preferred pattern is **list-all**: a `GET /api/<resource>` endpoint that returns all records keyed by `content_hash`. The caller discards what it doesn't need.

This is appropriate here because:
- The dataset is bounded (benchmark sets are hundreds of photos, not millions).
- Callers (e.g. the staging view) typically need most records anyway.
- It avoids URL length problems that arise when passing many 64-char SHA256 hashes as query parameters.

**URL length context:** nginx defaults to a 4 KB header buffer; AWS ALB caps at 16 KB. At 64 chars per SHA256 hash plus separators, the nginx default is exhausted at ~60 hashes. The old IE 2000-char limit is hit at ~30 hashes. These limits make `?hashes=h1,h2,...` fragile for any non-trivial list.

**Future escape hatch:** if the dataset grows to a point where list-all becomes too heavy, add a `POST /api/photos/query` endpoint accepting `{"hashes": [...]}` in the request body. POST with a JSON body has no length limit and is the pragmatic industry standard for bulk reads that don't fit in a URL (used by Elasticsearch `_mget`, most search APIs, etc.). The HTTP QUERY method — a safe+body method from an active IETF draft — is the principled future solution but has no browser or server support as of early 2026.

### Response shape for list-all endpoints

List endpoints return a JSON object keyed by full `content_hash`:

```json
{
  "abc123...": { "boxes": [...], "labeled": true },
  "def456...": { "boxes": [...], "labeled": false }
}
```

Single-item endpoints return the value directly (no outer wrapper).

---

## Endpoint inventory

### Bib boxes — `bib_bp` (`routes_bib.py`)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/bib_boxes` | All photos' bib boxes, keyed by hash. Returns `{boxes, labeled}` per photo. Excludes suggestions and split (labeling-UI concerns). |
| `GET` | `/api/bib_boxes/<hash>` | Single photo. Returns `{boxes, suggestions, tags, split, labeled}`. |
| `PUT` | `/api/bib_boxes/<hash>` | Save full bib box list for a photo. |
| `POST` | `/api/labels` | Set the bib `labeled` flag for a photo. |
| `GET` | `/api/bib_face_links/<hash>` | Get bib-face links for a photo. |
| `PUT` | `/api/bib_face_links/<hash>` | Save bib-face links for a photo. |

### Face boxes — `face_bp` (`routes_face.py`)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/face_boxes` | All photos' face boxes, keyed by hash. Returns `{boxes, labeled}` per photo. Excludes suggestions. |
| `GET` | `/api/face_boxes/<hash>` | Single photo. Returns `{boxes, suggestions, tags}`. |
| `PUT` | `/api/face_boxes/<hash>` | Save full face box list for a photo. |
| `POST` | `/api/face_labels` | Set the face `labeled` flag for a photo. |
| `GET` | `/api/identities` | List all named identities. |
| `POST` | `/api/identities` | Add a new identity. |
| `POST` | `/api/rename_identity` | Rename an existing identity. |
| `GET` | `/api/face_identity_suggestions/<hash>` | Face identity suggestions for a photo. |
| `GET` | `/api/face_crop/<hash>/<idx>` | Serve a cropped face image. |

### Benchmark / staging — `benchmark_bp` (`routes_benchmark.py`)

| Method | URL | Description |
|---|---|---|
| `POST` | `/api/freeze` | Freeze a named snapshot from a list of hashes. |

### Shared routes — `web_app.py`

| Method | URL | Description |
|---|---|---|
| `GET` | `/photo/<hash>` | Serve the full photo by content hash (not under `/api/`). |

---

## What is not yet implemented

The `GET /api/bib_boxes` and `GET /api/face_boxes` list-all endpoints are **planned but not yet implemented**. They are needed by the staging grid view (see staging UI task). The single-hash GET/PUT variants exist today.
