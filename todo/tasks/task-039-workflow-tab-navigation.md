# Task 039: Workflow tab navigation across labeling steps

Depends on task-038 (requires `CompletionService` and explicit `labeled` flags).

## Goal

Add a persistent tab bar and per-photo status strip to all three labeling interfaces
(bibs, faces, links). Switching tabs carries the current photo hash, so the user stays
on the same photo. The status strip shows completion state for each step and links
directly to that step for the current photo — making it easy to jump to an earlier step
to fix a mistake and return.

## Background

The three labeling interfaces are independent pages with no shared navigation. When a
user spots a labeling error from the linking view (e.g. a face is mislabeled), they
must navigate to the faces interface separately and find the photo again. The tab bar +
status strip eliminates this friction.

## Design

```
┌─────────────────────────────────────────────────────────┐
│  [ Bibs 142/180 ]  [ Faces 98/180 ]  [● Links 12/142 ]  │
├─────────────────────────────────────────────────────────┤
│  [abc1234]  bibs ✓  faces ✓  links —                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ← prev  photo 67/142   next →   next unlabeled →      │
│                                                         │
│   ┌─────────────────────────────────────────────┐       │
│   │                                             │       │
│   │              photo here                     │       │
│   │                                             │       │
│   └─────────────────────────────────────────────┘       │
│                                                         │
│   [ step-specific UI ]                                  │
│                                                         │
│                              [ Save ]                   │
└─────────────────────────────────────────────────────────┘
```

### Tab bar (top strip)

- Three tabs: **Bibs**, **Faces**, **Links**
- Each tab shows a progress badge: `done / total` for that step's queue
- Active tab is highlighted
- **Links tab is greyed / disabled** when the current photo is not yet link-ready
  (i.e. not in `CompletionService.get_link_ready_hashes()`)
- Clicking a tab navigates to `/{step}/{hash}` — same photo, different step

### Status strip (below tab bar)

- Shows the short hash `[abc1234]` and three per-step indicators:
  `bibs ✓ / ✗ / —`  `faces ✓ / ✗ / —`  `links ✓ / ✗ / —`
- ✓ = labeled/linked, — = not yet done, ✗ = not applicable (shouldn't occur normally)
- Each indicator is a link: clicking `faces ✓` goes to `/faces/{hash}`
- This is the primary fix-in-place mechanism: from the linking view, click `faces —`
  to jump to the face labeling page for the same photo

### Progress counts

Tab badges use counts from `CompletionService`:
- Bibs: photos with `bib_labeled=True` / total in index
- Faces: photos with `face_labeled=True` / total in index
- Links: photos with links saved / total link-ready photos

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Shared template or per-page include? | Shared Jinja2 partial `_workflow_nav.html`, included in all three labeling templates |
| How does the partial get its data? | Each route passes a `workflow` context dict (prepared by a helper, not inline in the route) |
| Where does the progress count logic live? | `CompletionService` — new methods `get_bib_progress()`, `get_face_progress()`, `get_link_progress()` returning `(done, total)` |
| Does the Links tab become a dead link when photo isn't ready? | It renders as `<span>` (not `<a>`) with a `disabled` CSS class — no broken URL |
| Full page navigation or JS tab switching? | Full page navigation (simple URLs, no JS complexity) |

## Changes: `benchmarking/services/completion_service.py`

### New functions

```python
def get_bib_progress() -> tuple[int, int]:
    """Returns (labeled_count, total_count)."""

def get_face_progress() -> tuple[int, int]:
    """Returns (labeled_count, total_count)."""

def get_link_progress() -> tuple[int, int]:
    """Returns (linked_count, link_ready_total)."""
```

### New helper

```python
def workflow_context_for(content_hash: str, active_step: str) -> dict:
    """Build the `workflow` dict passed to all labeling templates.

    active_step: one of 'bibs', 'faces', 'links'
    Returns dict with keys: active_step, bib_progress, face_progress, link_progress,
    bib_labeled, face_labeled, links_saved, link_ready.
    """
```

## Changes: `benchmarking/templates/`

### New partial: `_workflow_nav.html`

Renders the tab bar and status strip from the `workflow` context dict. Included at the
top of `bib_labeling.html`, `face_labeling.html`, and `link_labeling.html`.

Tab bar structure:
```html
<nav class="workflow-tabs">
  <a href="/bibs/{{ hash }}" class="tab {% if active == 'bibs' %}active{% endif %}">
    Bibs <span class="badge">{{ bib_progress.done }}/{{ bib_progress.total }}</span>
  </a>
  <a href="/faces/{{ hash }}" class="tab {% if active == 'faces' %}active{% endif %}">
    Faces <span class="badge">{{ face_progress.done }}/{{ face_progress.total }}</span>
  </a>
  {% if link_ready %}
  <a href="/associations/{{ hash }}" class="tab {% if active == 'links' %}active{% endif %}">
    Links <span class="badge">{{ link_progress.done }}/{{ link_progress.total }}</span>
  </a>
  {% else %}
  <span class="tab disabled">
    Links <span class="badge">{{ link_progress.done }}/{{ link_progress.total }}</span>
  </span>
  {% endif %}
</nav>

<div class="photo-status-strip">
  <code>{{ content_hash[:8] }}</code>
  <a href="/bibs/{{ hash }}">bibs {{ '✓' if bib_labeled else '—' }}</a>
  <a href="/faces/{{ hash }}">faces {{ '✓' if face_labeled else '—' }}</a>
  {% if link_ready %}
  <a href="/associations/{{ hash }}">links {{ '✓' if links_saved else '—' }}</a>
  {% else %}
  <span>links —</span>
  {% endif %}
</div>
```

### Modified: `bib_labeling.html`, `face_labeling.html`, `link_labeling.html`

Add `{% include '_workflow_nav.html' %}` at the top of the content area.

## Changes: `benchmarking/routes/ui/labeling.py`

### Modified: `bib_photo()`, `face_photo()`, `association_photo()`

Each route calls `workflow_context_for(full_hash, active_step='bibs'/'faces'/'links')`
and merges the result into the template context:

```python
from benchmarking.services.completion_service import workflow_context_for

context = {
    ...existing keys...,
    'workflow': workflow_context_for(full_hash, 'links'),
}
```

Routes do **not** compute progress counts or status flags inline.

## Tests

`tests/test_completion_service.py` (extend from task-038):

- `test_get_bib_progress_counts()` — returns correct (done, total)
- `test_get_face_progress_counts()` — returns correct (done, total)
- `test_get_link_progress_counts()` — denominator is link-ready total, not all photos
- `test_workflow_context_for_bib_step()` — active_step='bibs', correct flags
- `test_workflow_context_for_links_disabled_when_not_ready()` — link_ready=False

No browser/E2E tests required — visual correctness is confirmed manually.

## Scope boundaries

- **In scope**: tab bar + status strip template partial, progress counts in `CompletionService`, route context changes
- **Out of scope**: JS tab switching, URL restructure (task-022), benchmark/run views
- **Do not** change the labeling UI beyond adding the nav partial
- **Do not** implement tab switching without a full page load — keep it simple
