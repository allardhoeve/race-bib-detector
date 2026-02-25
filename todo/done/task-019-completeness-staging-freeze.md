# Task 019: Photo completeness tracking and staging/freeze UI

Depends on task-006 (`sets.py`, `freeze()`), task-007 (`LinkGroundTruth`),
task-008 (link API), task-009 (link UI). Independent of tasks 011–018.

Task-006 leaves `cmd_freeze()` as a minimal stub (freezes all photos, no filtering).
This task **replaces that stub** with the completeness-aware implementation and adds
the `--all` and `--include-incomplete` subparser flags.

## Goal

Introduce a `PhotoCompleteness` model that tracks whether each photo has been
labeled in all three dimensions (bib, face, links), and expose it through a
`/staging/` page that acts as the completeness dashboard and gateway to freezing
a named benchmark snapshot.

## Background

The labeling workflow has three independent steps — bib labeling, face labeling,
and bib-face link labeling — that can be done in any order and for different
photo subsets. A photo labeled in only one dimension is silently treated by the
benchmark runner as having zero ground truth in the other dimensions, degrading
scoring accuracy without any visible warning. The staging page makes this gap
explicit before a freeze is committed.

The CLI `freeze` command (task-006) currently checks only whether a photo is bib-
labeled. This task extends it to require all three dimensions or to prompt the
operator with a summary of incomplete photos.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where is completeness stored? | Derived at query time — no new JSON file, no staleness risk |
| What counts as face-labeled? | `is_face_labeled(label)` from `label_utils.py` (boxes or tags present) |
| What counts as links-labeled? | If bib_box_count == 0 OR face_box_count == 0 → trivially True; otherwise a `LinkGroundTruth` entry must exist |
| What if task-007/008/009 are not done? | `links_labeled` defaults to True — links step treated as N/A |
| Known negatives | bib_labeled AND face_labeled AND bib_box_count == 0 AND face_box_count == 0 |
| Freeze from web UI | `POST /api/freeze` in `routes_benchmark.py` calls `sets.freeze()` |
| Staging route location | Blueprint `benchmark` — `GET /staging/` |
| CLI guard | `cmd_freeze()` filters on `is_complete`; `--include-incomplete` bypasses with a warning |

## Changes: `benchmarking/completeness.py` (new file)

```python
"""Per-photo completeness model: tracks whether all labeling dimensions are done."""
from __future__ import annotations

from dataclasses import dataclass

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
)
from benchmarking.label_utils import is_face_labeled
from benchmarking.photo_index import load_photo_index


@dataclass
class PhotoCompleteness:
    content_hash: str
    bib_labeled: bool
    face_labeled: bool
    links_labeled: bool   # True when trivially N/A (0 bib or face boxes) or GT entry exists
    bib_box_count: int
    face_box_count: int

    @property
    def is_complete(self) -> bool:
        return self.bib_labeled and self.face_labeled and self.links_labeled

    @property
    def is_known_negative(self) -> bool:
        """Both dimensions labeled and both have zero boxes — no link step needed."""
        return (
            self.bib_labeled
            and self.face_labeled
            and self.bib_box_count == 0
            and self.face_box_count == 0
        )


def photo_completeness(content_hash: str) -> PhotoCompleteness:
    """Compute completeness for a single photo from all GT stores."""
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    bib_label = bib_gt.get_photo(content_hash)
    face_label = face_gt.get_photo(content_hash)

    bib_labeled = bool(bib_label and bib_label.labeled)
    face_labeled = bool(face_label and is_face_labeled(face_label))

    bib_box_count = len(bib_label.boxes) if bib_label else 0
    face_box_count = len(face_label.boxes) if face_label else 0

    # links_labeled: trivially True when no bib or face boxes exist
    if bib_box_count == 0 or face_box_count == 0:
        links_labeled = True
    else:
        # Requires task-007 LinkGroundTruth; gracefully defaults to True if unavailable
        try:
            from benchmarking.ground_truth import load_link_ground_truth
            link_gt = load_link_ground_truth()
            links_labeled = content_hash in link_gt.photos
        except (ImportError, AttributeError):
            links_labeled = True

    return PhotoCompleteness(
        content_hash=content_hash,
        bib_labeled=bib_labeled,
        face_labeled=face_labeled,
        links_labeled=links_labeled,
        bib_box_count=bib_box_count,
        face_box_count=face_box_count,
    )


def get_all_completeness() -> list[PhotoCompleteness]:
    """Return completeness for every photo that has at least one labeling dimension done.

    Only photos that appear in the bib or face GT are included — unlabeled photos
    are not shown because they have not been touched at all.
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    touched = set(bib_gt.photos) | set(face_gt.photos)
    return [photo_completeness(h) for h in sorted(touched)]
```

## Changes: `benchmarking/routes_benchmark.py`

### New route: `GET /staging/`

Add to the `benchmark` blueprint:

```python
@benchmark_bp.route("/staging/")
def staging():
    from benchmarking.completeness import get_all_completeness
    rows = get_all_completeness()
    index = load_photo_index()
    return render_template(
        "staging.html",
        rows=rows,
        index=index,
    )
```

### New endpoint: `POST /api/freeze`

Requires task-006 `sets.py`. Add to the `benchmark` blueprint:

```python
@benchmark_bp.route("/api/freeze", methods=["POST"])
def api_freeze():
    from benchmarking.sets import freeze
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    description = data.get("description", "")
    hashes = data.get("hashes", [])

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not hashes:
        return jsonify({"error": "hashes list is empty"}), 400

    index = load_photo_index()
    subset = {h: index[h] for h in hashes if h in index}

    try:
        snapshot = freeze(
            name=name,
            hashes=sorted(subset.keys()),
            index=subset,
            description=description,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify(snapshot.metadata.to_dict()), 200
```

## Changes: `benchmarking/templates/staging.html` (new file)

The template extends `base.html` (or equivalent) and renders:

- **Filter tabs**: All | Ready (is_complete) | Incomplete | Known-negatives
- **Table**: one row per photo with columns:
  - Thumbnail (small, linked to the photo's artifact page)
  - Bib status: green check / red X with link to `/labels/<hash>/`
  - Face status: green check / red X with link to `/faces/labels/<hash>/`
  - Links status: green check / red X / grey dash (N/A) with link to bib labeling page
  - Overall: "Ready", "Incomplete", or "Known-negative" badge
- **Freeze form** (below table, only shown when any row is selected):
  - Checkbox column to select rows
  - Name input, optional description textarea
  - "Freeze selected" submit button (calls `POST /api/freeze` via fetch)
  - Response: shows snapshot metadata or error message inline

Known-negative rows use a grey/neutral style (not the same red as incomplete), since
they are correctly labeled.

Incomplete rows link directly to the first unfinished labeling page for that photo so
the operator can fix the gap in one click.

## Changes: `benchmarking/cli.py`

### Updated: `cmd_freeze()` (replaces task-006 stub)

Replace task-006's minimal stub (which froze all photos without filtering) with a call
to `get_all_completeness()` and honour the new `--all` / `--include-incomplete` flags:

```python
def cmd_freeze(args: argparse.Namespace) -> int:
    from benchmarking.sets import freeze
    from benchmarking.completeness import get_all_completeness
    import re

    name = args.name
    description = args.description or ""

    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        print(f"Error: name must be alphanumeric with hyphens/underscores: {name!r}")
        return 1

    index = load_photo_index()
    if not index:
        print("Error: no photos in index. Run 'bnr benchmark scan' first.")
        return 1

    if args.all:
        hashes = sorted(index.keys())
    else:
        rows = get_all_completeness()
        complete = [r for r in rows if r.is_complete or r.is_known_negative]
        incomplete = [r for r in rows if not r.is_complete and not r.is_known_negative]

        if incomplete and not args.include_incomplete:
            print(f"Warning: {len(incomplete)} photos are not fully labeled:")
            for r in incomplete[:10]:
                dims = []
                if not r.bib_labeled:
                    dims.append("bib")
                if not r.face_labeled:
                    dims.append("face")
                if not r.links_labeled:
                    dims.append("links")
                print(f"  {r.content_hash[:8]}  missing: {', '.join(dims)}")
            if len(incomplete) > 10:
                print(f"  ... and {len(incomplete) - 10} more")
            print("Use --include-incomplete to freeze anyway.")
            return 1

        hashes = sorted(r.content_hash for r in complete)
        if args.include_incomplete:
            hashes = sorted(r.content_hash for r in rows)

        if not hashes:
            print("No labeled photos to freeze. Use --all to include all photos.")
            return 1

    try:
        snapshot = freeze(
            name=name,
            hashes=hashes,
            index={h: index[h] for h in hashes if h in index},
            description=description,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Snapshot '{name}' created:")
    print(f"  Photos: {snapshot.metadata.photo_count}")
    print(f"  Path:   {snapshot.path}")
    return 0
```

### Updated: subparser for `freeze`

Add `--all` and `--include-incomplete` to the subparser created in task-006:

```python
freeze_parser.add_argument(
    "--all",
    action="store_true",
    help="Freeze every photo in the index regardless of labeling status",
)
freeze_parser.add_argument(
    "--include-incomplete",
    action="store_true",
    help="Include photos that are not fully labeled in all dimensions",
)
```

## Changes: `benchmarking/templates/labels_home.html`

Add a staging card as "Step 4 — Staging & Freeze":

```html
<div class="card">
  <h2>Step 4 — Staging &amp; Freeze</h2>
  <p>Review completeness across all labeling dimensions and create a frozen
     benchmark snapshot when all photos are ready.</p>
  <a href="{{ url_for('benchmark.staging') }}" class="btn">Open Staging</a>
</div>
```

## Tests

Add `tests/test_completeness.py`:

- `test_photo_completeness_all_done()` — bib + face GT populated with boxes, link GT
  entry exists → `is_complete=True`, all three flags True.
- `test_photo_completeness_bib_only()` — only bib labeled → `is_complete=False`,
  `face_labeled=False`.
- `test_photo_completeness_face_only()` — only face labeled → `is_complete=False`,
  `bib_labeled=False`.
- `test_photo_completeness_known_negative()` — both labeled, 0 boxes each →
  `is_known_negative=True`, `links_labeled=True` (trivial), `is_complete=True`.
- `test_photo_completeness_links_trivial()` — bib has boxes, face has 0 boxes →
  `links_labeled=True` without any link GT entry.
- `test_get_all_completeness_only_touched()` — a photo in neither GT is not returned.

Add to `tests/test_web_app.py`:

- `test_staging_route_200()` — `GET /staging/` returns 200.
- `test_api_freeze_creates_snapshot(tmp_path, monkeypatch)` — POST `/api/freeze`
  with valid hashes and monkeypatched `FROZEN_DIR` → 200 and snapshot metadata in
  response body.
- `test_api_freeze_conflict(tmp_path, monkeypatch)` — POST `/api/freeze` with a
  name that already exists → 409.
- `test_api_freeze_missing_name()` — POST with empty name → 400.

## Scope boundaries

- **In scope**: `completeness.py` module; `GET /staging/` route and template;
  `POST /api/freeze` endpoint; replacement of task-006's `cmd_freeze()` stub with
  completeness-aware logic; adding `--all` and `--include-incomplete` subparser flags;
  staging card in `labels_home.html`.
- **Out of scope**: using frozen sets in `run_benchmark()` (separate task); showing
  per-snapshot run history; editing or deleting frozen snapshots.
- **Do not** modify the bib or face GT schemas, `sets.py`, or existing route logic
  beyond adding the new routes and the card.
- The `links_labeled` dimension degrades gracefully: if task-007 is not yet merged,
  `load_link_ground_truth` will not exist and the `except ImportError` path returns
  `True`, keeping the staging page usable.
