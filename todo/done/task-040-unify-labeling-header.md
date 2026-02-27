# Task 040: Unify labeling page header into shared partial

UI maintenance. Independent of all other pending tasks.

## Goal

Extract the `.header` block shared by all three labeling pages (bib, face, link)
into a single `_labeling_header.html` include. This prevents the recurring bug
where a structural change to one header (e.g. adding a filter dropdown) silently
diverges from the others.

## Background

All three labeling pages have the same header structure:

```
.header
  .nav-info          ← page-specific nav links + shared Prev/Next/Unlabeled buttons
  .filter-section    ← filter <select> (options differ per page)
```

A recent bug: the filter dropdown for link labeling was placed inside `.nav-info`
instead of as a sibling `.filter-section`. There was no shared template to
enforce the correct structure, so the mistake wasn't caught until manual review.

The root cause of divergence: the three pages call different JS navigate functions:

| Page | Prev/Next onclick | Reason |
|------|------------------|--------|
| bib labeling | `navigate('prev')` | reads URL from PAGE_DATA internally |
| face labeling | `navigate('prev')` | same |
| link labeling | `navigateLink(PAGE_DATA.prevUrl)` | must flush pending saves first |

Step 1 normalises this. Step 2 extracts the partial.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| How to unify JS navigate? | Rename `navigate(direction)` → `navigate(url)` in `labeling.js`; rename `navigateLink` → `navigate` in `link_labeling_ui.js` (loaded after, so it overrides the simple version for the link page). All templates then call `navigate(PAGE_DATA.prevUrl)`. |
| How to pass page-specific content into the partial? | Use Jinja2 `{% set var %}...{% endset %}` blocks before the `{% include %}`. The partial reads `nav_links`, `filter_options`, and `extra_buttons`. |
| What about `applyFilter()`? | It stays in `labeling.js` but changes to navigate to the index URL using the filter value. For link labeling, `link_labeling_ui.js` already exposes its own `applyFilter` that overrides. After this task, both can use the same function since the index URL pattern is the same. See step 3 below. |
| Keep `navigateUnlabeled()`? | Yes — it reads `PAGE_DATA.nextUnlabeledUrl` and calls `navigate(url)`. Callers in the partial use it unchanged. |

## Step 1: Normalize JS navigate functions

### Changes: `benchmarking/static/labeling.js`

```js
// Before:
function navigate(direction) {
    const url = direction === 'prev' ? PAGE_DATA.prevUrl : PAGE_DATA.nextUrl;
    if (url) window.location.href = url;
}

// After:
function navigate(url) {
    if (url) window.location.href = url;
}
```

`navigateUnlabeled()` stays the same (already calls navigate with a URL after
this change, since it passes `PAGE_DATA.nextUnlabeledUrl`).

### Changes: `benchmarking/static/link_labeling_ui.js`

Rename `navigateLink` → `navigate` everywhere in the file. The save-before-navigate
logic is unchanged; only the function name changes. Since `link_labeling_ui.js` loads
after `labeling.js`, the IIFE's `window.navigate = navigate` assignment overrides the
simpler version for the link page only.

Update the `window.navigateLink = navigateLink` export line to `window.navigate = navigate`.

### Changes: `benchmarking/templates/labeling.html`

Replace all `navigate('prev')` → `navigate(PAGE_DATA.prevUrl)` and
`navigate('next')` → `navigate(PAGE_DATA.nextUrl)`.

### Changes: `benchmarking/templates/face_labeling.html`

Same replacements as labeling.html.

### Changes: `benchmarking/templates/link_labeling.html`

Replace all `navigateLink(...)` → `navigate(...)`. The argument is already a URL
in all call sites, so no further changes needed.

## Step 2: Extract `_labeling_header.html`

### New file: `benchmarking/templates/_labeling_header.html`

```html
{#
  Shared labeling page header. Set these variables before including:

    nav_links      — HTML block: page-specific <a class="nav-link"> elements
    filter_options — list of {value, label} dicts for the <select>
    filter         — currently selected filter value (string)
    current        — int: current photo index (1-based)
    total          — int: total photos in filtered list
    prev_url       — string|None
    next_url       — string|None
    next_unlabeled_url — string|None (optional)
    extra_buttons  — HTML block: additional nav buttons (optional, default '')
#}
{% set extra_buttons = extra_buttons | default('') %}
<div class="header">
    <div class="nav-info">
        {{ nav_links }}
        <button class="nav-btn" {{ 'disabled' if not prev_url else '' }}
                onclick="navigate(PAGE_DATA.prevUrl)">← Prev</button>
        <span class="position">{{ current }} / {{ total }}</span>
        <button class="nav-btn" {{ 'disabled' if not next_url else '' }}
                onclick="navigate(PAGE_DATA.nextUrl)">Next →</button>
        {% if next_unlabeled_url %}
        <button class="nav-btn" onclick="navigateUnlabeled()">Next unlabeled →→</button>
        {% endif %}
        {{ extra_buttons }}
    </div>
    <div class="filter-section" style="background: transparent; border: none; padding: 0;">
        <select class="filter-select" style="width: auto;" id="filter" onchange="applyFilter()">
            {% for opt in filter_options %}
            <option value="{{ opt.value }}" {{ 'selected' if filter == opt.value else '' }}>{{ opt.label }}</option>
            {% endfor %}
        </select>
    </div>
</div>
```

### Changes: `benchmarking/templates/labeling.html`

Replace the `<div class="header">...</div>` block with:

```html
{% set nav_links %}
<a href="{{ request.url_for('benchmark_list') }}" class="nav-link">← Benchmarks</a>
<a href="{{ request.url_for('faces_index') }}" class="nav-link">Face Labels →</a>
<a href="{{ request.url_for('association_photo', content_hash=content_hash[:8]) }}" class="nav-link">Links ⇄</a>
{% endset %}
{% set filter_options = [
    {'value': 'all',       'label': 'All photos'},
    {'value': 'unlabeled', 'label': 'Unlabeled only'},
    {'value': 'labeled',   'label': 'Labeled only'},
] %}
{% include '_labeling_header.html' %}
```

### Changes: `benchmarking/templates/face_labeling.html`

Same pattern, different nav links and same filter options (all/unlabeled/labeled).

### Changes: `benchmarking/templates/link_labeling.html`

```html
{% set nav_links %}
<a href="{{ request.url_for('bib_photo', content_hash=content_hash[:8]) }}" class="nav-link">← Bib Labels</a>
<a href="{{ request.url_for('face_photo', content_hash=content_hash[:8]) }}" class="nav-link">Face Labels →</a>
{% endset %}
{% set extra_buttons %}
{% if next_incomplete_url %}
<button class="nav-btn" onclick="navigate('{{ next_incomplete_url }}')">Next incomplete →→</button>
{% endif %}
{% endset %}
{% set filter_options = [
    {'value': 'all',         'label': 'All'},
    {'value': 'unlinked',    'label': 'Unlinked'},
    {'value': 'underlinked', 'label': 'Incomplete'},
] %}
{% include '_labeling_header.html' %}
```

Note: `next_unlabeled_url` is still passed as a template variable and rendered by
the shared partial. `next_incomplete_url` goes into `extra_buttons`.

## Step 3: Unify `applyFilter()` (optional, do if easy)

Currently `labeling.js` has:
```js
function applyFilter() {
    const newFilter = document.getElementById('filter').value;
    window.location.href = PAGE_DATA.labelsIndexUrl + '?filter=' + newFilter;
}
```

And `link_labeling_ui.js` has its own `applyFilter` that navigates to `/associations/`.

If `PAGE_DATA` for link labeling includes `labelsIndexUrl: '/associations/'`, the
`link_labeling_ui.js` override can be removed and the shared function handles all three.

Check `labeling.html` and `face_labeling.html` to confirm `labelsIndexUrl` is already
in PAGE_DATA, then add it for link labeling. Remove the `window.applyFilter` override
from `link_labeling_ui.js`.

This is a **bonus step** — do it if it falls out naturally; skip if it complicates things.

## Tests

No new unit tests needed — this is a pure template/JS refactor.

Manual verification:
- Open `/bibs/`, `/faces/`, `/associations/` — headers look identical in structure
- Prev/Next navigation works on all three pages
- "Next unlabeled →→" works on bib and face pages
- "Next incomplete →→" works on link page
- Filter dropdown is on the right on all three pages
- Filter changes navigate correctly
- Link labeling: adding a link then clicking Next still flushes the save first
- Browser console: no JS errors on any page

Run `venv/bin/python -m pytest tests/test_web_app.py -q` — should pass unchanged.

## Scope boundaries

- **In scope**: `labeling.js`, `link_labeling_ui.js`, the three labeling templates,
  new `_labeling_header.html`
- **Out of scope**: `LabelingCore`, `LabelingUI`, API routes, ground truth, scoring
- **Do not** touch `bib_labeling_ui.js` or `face_labeling_ui.js` — they don't contain navigate functions
- **Do not** change PAGE_DATA keys that tests depend on
