# Task 020: Redesign home page as a numbered workflow with progress stats

Independent of tasks 008–019. Can be done at any time; task-019 depends on the
result of this task (see Scope boundaries).

## Goal

Restructure `labels_home.html` from three equal navigation cards into a four-step
numbered workflow with per-step completion counts. Move the Benchmarks link to the
page header. Show Step 4 (Freeze) as a grayed-out placeholder until task-019
implements it.

## Background

The current home page presents Bib Labels, Face Labels, and Benchmarks as equal
parallel options. The actual workflow is sequential: tag bibs → tag faces → link
bibs to faces → freeze. Presenting it as a pipeline makes the operator's position
in the process obvious and surfaces gaps (e.g. 87 faces labeled but 0 links) before
a freeze is attempted.

Benchmarks (run inspection) is not a labeling step; moving it to a header link
keeps the card grid focused on the four workflow steps.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Progress granularity | Per-step counts: `N / total` photos done in that dimension |
| Step 3 when link GT absent | Show `N/A` — graceful fallback, `links_labeled=None` from route |
| Step 4 before task-019 | Grayed-out card, `opacity: 0.5; pointer-events: none`, no href |
| Benchmarks placement | Right side of home page header bar (`<a class="nav-link">`) |
| base.html changes | None — each page owns its own header block |
| Step 3 link target | `/links/` (task-009 route); card is active/linked even if route not yet live |

## Changes: `benchmarking/web_app.py`

### Modified: `index()`

Replace the bare `render_template` call with one that passes progress stats:

```python
@app.route('/')
def index():
    """Landing page — numbered labeling workflow with per-step progress."""
    from benchmarking.ground_truth import load_bib_ground_truth, load_face_ground_truth
    from benchmarking.label_utils import is_face_labeled

    photo_index = load_photo_index()
    total = len(photo_index)

    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    bib_labeled = sum(1 for lbl in bib_gt.photos.values() if lbl.labeled)
    face_labeled = sum(1 for lbl in face_gt.photos.values() if is_face_labeled(lbl))

    try:
        from benchmarking.ground_truth import load_link_ground_truth
        link_gt = load_link_ground_truth()
        links_labeled = len(link_gt.photos)
    except (ImportError, AttributeError):
        links_labeled = None   # template renders as "N/A"

    return render_template(
        'labels_home.html',
        total=total,
        bib_labeled=bib_labeled,
        face_labeled=face_labeled,
        links_labeled=links_labeled,
    )
```

## Changes: `benchmarking/templates/labels_home.html`

Full restructure. The rendered page should look like:

```
┌────────────────────────────────────────────────────────┐
│  Benchmark Labeling                  View Benchmarks →  │  ← header
├────────────────────────────────────────────────────────┤
│  Labeling workflow                                      │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ Step 1   │  │ Step 2   │  │ Step 3   │  │Step 4  │  │
│  │ Bib      │  │ Face     │  │ Links    │  │Freeze  │  │
│  │ Labels   │  │ Labels   │  │          │  │(soon)  │  │
│  │ 142/250  │  │  87/250  │  │  0/250   │  │ gray   │  │
│  │ Start →  │  │ Start →  │  │ Start →  │  │        │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
└────────────────────────────────────────────────────────┘
```

Implementation notes:
- Progress stat: `<span class="progress">{{ bib_labeled }} / {{ total }}</span>` (small,
  muted colour) rendered below the card description, above the CTA link.
- Step 3 progress: `{% if links_labeled is none %}N/A{% else %}{{ links_labeled }} / {{ total }}{% endif %}`
- Step 4 card: add `class="card card--disabled"` with CSS `opacity: 0.5; pointer-events: none`.
  No `<a>` link inside it. Description: "Coming soon — freeze a named benchmark snapshot
  when all photos are ready."
- "View Benchmarks →" goes in the right side of the `.header` div as `<a class="nav-link">`.

## Tests

Add to `tests/test_web_app.py`:

- `test_home_route_200()` — `GET /` returns 200.
- `test_home_route_shows_progress(client, monkeypatch)` — monkeypatch
  `load_bib_ground_truth` and `load_face_ground_truth` to return one labeled photo
  each out of two total photos; assert response body contains `"1 / 2"`.
- `test_home_route_links_na(client, monkeypatch)` — monkeypatch to raise
  `ImportError` on `load_link_ground_truth`; assert response body contains `"N/A"`.

## Scope boundaries

- **In scope**: `web_app.py` `index()` route; `labels_home.html` restructure;
  two tests added to `test_web_app.py`.
- **Out of scope**: changes to any other template, blueprint, or route;
  making Step 3 or Step 4 cards fully functional (that is task-009 and task-019).
- **Do not** modify `base.html`, any labeling page, or any other template.
- **Task-019 overlap**: task-019's "Changes: `labels_home.html`" section (which adds
  a Step 4 card) is **superseded by this task**. When implementing task-019, skip
  that section and instead update the already-present Step 4 card to add the
  `url_for('benchmark.staging')` link and remove the `card--disabled` class.
