# Task 005a: Extract templates and inline JS from web_app.py

Part 1 of 3 — see also [005b](../tasks/task-005b-blueprint-route-split.md), [005c](../tasks/task-005c-extract-helpers-cleanup.md).

## Goal

Move all inline HTML templates and inline `<script>` blocks out of
`benchmarking/web_app.py` into Jinja2 template files and static JS files.
Pure extraction — no behavior changes.

## Background

`web_app.py` is 2604 lines. ~1800 of those are inline template strings and
inline JS. Extracting them shrinks the Python file to ~800 lines and makes
templates editable with proper syntax highlighting.

### Current file layout

```
benchmarking/
  web_app.py          ← 2604 lines (the target)
  static/
    labeling.js       ← existing canvas UI (LabelingUI, LabelingCore)
    test_labeling.html
  templates/          ← does NOT exist yet (create in setup)
```

### Test safety

All 31 tests in `tests/test_web_app.py` hit **JSON API endpoints only**
(`/api/bib_boxes/`, `/api/labels`, etc.). Zero tests render or check HTML
from the template routes (`/`, `/labels/`, `/benchmark/`, `/faces/`).
Template extraction cannot break any existing tests. Manual browser testing
is needed after each step for visual verification.

## Key decisions

| Decision | Resolution |
|----------|-----------|
| Does `empty.html` extend `base.html`? | **No** — it has its own independent styles and does not use `COMMON_STYLES` |
| Keep `serve_static` route or switch to Flask built-in? | **Keep `serve_static` in 005a**. Templates must use `url_for('serve_static', ...)`. Defer switch to 005c |
| Deduplicate shared JS across bib/face? | **No** — pure extraction, no behavior changes. Note duplication for follow-up |
| Hardcoded `/api/` fetch paths in face JS? | **Keep as-is** — they are not Jinja2 and work in static JS. Document coupling |
| `template_folder` on Flask constructor? | Flask resolves templates relative to the package. `benchmarking/templates/` is the default for `Flask(__name__)` when `__name__` is `benchmarking.web_app`. **Explicit `template_folder` not needed**, but add it for clarity |

## Approach

Work **one template at a time**, in order of complexity. Run
`pytest tests/test_web_app.py` after each.

---

### Step 0 — Setup

**0a.** Create `benchmarking/templates/` directory.

**0b.** Create `benchmarking/templates/base.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}Benchmark{% endblock %}</title>
    <style>
        /* paste COMMON_STYLES from web_app.py lines 67-178 here verbatim */
        {% block extra_styles %}{% endblock %}
    </style>
</head>
<body>
    {% block body %}{% endblock %}
</body>
</html>
```

Block structure:
- `{% block title %}` — page-specific `<title>`
- `{% block extra_styles %}` — per-page CSS (inside the existing `<style>` tag)
- `{% block body %}` — full `<body>` contents

**0c.** In `web_app.py`, change the Flask constructor (line 1884):

```python
# Before
app = Flask(__name__)

# After
app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / 'templates'),
)
```

**0d.** Add `render_template` to the flask imports (line 24-34), keeping
`render_template_string` until all templates are converted:

```python
from flask import (
    Flask,
    render_template,          # ← add
    render_template_string,   # ← keep for now
    ...
)
```

**0e.** Run `pytest tests/test_web_app.py` — should pass (no behavior change).

---

### Step 1 — `EMPTY_TEMPLATE` → `templates/empty.html`

**Source**: lines 1840-1875. Does **NOT** use `COMMON_STYLES`. Standalone.
Does **NOT** extend `base.html`.

**1a.** Create `benchmarking/templates/empty.html` — copy the HTML verbatim
from the string (strip the `"""` delimiters). No Jinja2 variables used.

**1b.** Replace all 4 call sites in `create_app()`:

```python
# Lines 1909, 1920, 2026, 2037 — each is:
return render_template_string(EMPTY_TEMPLATE)
# → becomes:
return render_template('empty.html')
```

**1c.** Delete the `EMPTY_TEMPLATE` constant (lines 1840-1875).

**1d.** Run `pytest tests/test_web_app.py`.

---

### Step 2 — `LABELS_HOME_TEMPLATE` → `templates/labels_home.html`

**Source**: lines 185-264. Uses `COMMON_STYLES` via string concat (line 191).
Has Jinja2 `{{ url_for(...) }}` in `<a href>` tags but **no inline JS**.

**2a.** Create `benchmarking/templates/labels_home.html`:

```html
{% extends "base.html" %}
{% block title %}Benchmark Labeling{% endblock %}
{% block extra_styles %}
        /* paste the per-page CSS from lines 192-232 */
{% endblock %}
{% block body %}
    <!-- paste <body> contents from lines 236-261 -->
{% endblock %}
```

Jinja2 expressions to preserve in the HTML (no changes needed):
- `{{ url_for('labels_index') }}` (line 248)
- `{{ url_for('face_labels_index') }}` (line 253)
- `{{ url_for('benchmark_list') }}` (line 258)

**2b.** In `create_app()`, change the call site (line 1892):

```python
# Before
return render_template_string(LABELS_HOME_TEMPLATE)
# After
return render_template('labels_home.html')
```

**2c.** Delete the `LABELS_HOME_TEMPLATE` constant (lines 185-264).

**2d.** Run `pytest tests/test_web_app.py`.

---

### Step 3 — `BENCHMARK_LIST_TEMPLATE` → `templates/benchmark_list.html`

**Source**: lines 1309-1437. Uses `COMMON_STYLES` (line 1315). No inline JS.
Template variable: `runs` (list of dicts).

**3a.** Create `benchmarking/templates/benchmark_list.html`:

```html
{% extends "base.html" %}
{% block title %}Benchmark Runs{% endblock %}
{% block extra_styles %}
        /* paste per-page CSS from lines 1316-1376 */
{% endblock %}
{% block body %}
    <!-- paste <body> contents from lines 1379-1434 -->
{% endblock %}
```

Jinja2 expressions to preserve in the HTML:
- `{{ url_for('labels_index') }}` (line 1381)
- `{{ url_for('benchmark_inspect', run_id=run.run_id) }}` (line 1408)
- `{% if runs %}` / `{% for run in runs %}` / `{% endfor %}` / `{% else %}` (loop)
- Various `{{ run.* }}` fields and `{{ "%.1f%%"|format(...) }}` formatters

**3b.** Change call site (line 2360):

```python
# Before
return render_template_string(BENCHMARK_LIST_TEMPLATE, runs=runs)
# After
return render_template('benchmark_list.html', runs=runs)
```

**3c.** Delete the `BENCHMARK_LIST_TEMPLATE` constant (lines 1309-1437).

**3d.** Run `pytest tests/test_web_app.py`.

---

### Step 4 — `BENCHMARK_INSPECT_TEMPLATE` → `templates/benchmark_inspect.html` + `static/benchmark_inspect.js`

**Source**: lines 1444-1837. Uses `COMMON_STYLES` (line 1450).
Inline `<script>` at lines 1667-1834 (168 lines, no external script
dependency — does NOT load `labeling.js`).

#### 4a. Identify Jinja2 expressions in the JS block

The script uses `{{ ... }}` in these places:

| JS line | Expression | PAGE_DATA key |
|---------|-----------|---------------|
| 1668 | `{{ photo_results_json \| safe }}` | `photoResults` |
| 1669 | `{{ run.metadata.run_id }}` | `runId` |
| 1670 | `{{ current_idx }}` | `currentIdx` |
| 1779 | `{{ url_for('labels_index') }}` | `editLinkBase` |
| 1789 | `{{ url_for('serve_photo', content_hash='HASH') }}` | `photoUrlTemplate` |
| 1791-1794 | `{{ url_for('serve_artifact', run_id='RUN', hash_prefix='HASH', image_type='TYPE') }}` | `artifactUrlTemplate` |
| 1814 | `{{ url_for('benchmark_inspect', run_id=run.metadata.run_id) }}` | `inspectUrl` |
| 1819 | `{{ url_for('benchmark_list') }}` | `benchmarkListUrl` |

**Note on URL templates**: Lines 1789 and 1791-1794 generate URLs with
placeholder values (`'HASH'`, `'RUN'`, `'TYPE'`) and then use
`.replace('HASH', hash)` client-side. The PAGE_DATA must pass these URL
patterns as strings with the placeholders intact.

**Note on `| safe`**: `photo_results_json` uses `| safe` to bypass Jinja2
escaping. This is intentional — the data comes from the benchmark runner,
not user input. In the PAGE_DATA block, use `{{ photo_results_json | safe }}`
(not `| tojson`, since it's already JSON-serialized in Python).

#### 4b. Create the PAGE_DATA block in `templates/benchmark_inspect.html`

```html
{% extends "base.html" %}
{% block title %}Inspect - {{ run.metadata.run_id }}{% endblock %}
{% block extra_styles %}
        /* paste per-page CSS from lines 1451-1664 */
{% endblock %}
{% block body %}
    <!-- paste <body> contents from lines 1467-1665 -->

    <script>
      window.PAGE_DATA = {
        photoResults:        {{ photo_results_json | safe }},
        runId:               '{{ run.metadata.run_id }}',
        currentIdx:          {{ current_idx }},
        editLinkBase:        '{{ url_for("labels_index") }}',
        photoUrlTemplate:    '{{ url_for("serve_photo", content_hash="HASH") }}',
        artifactUrlTemplate: '{{ url_for("serve_artifact", run_id="RUN", hash_prefix="HASH", image_type="TYPE") }}',
        inspectUrl:          '{{ url_for("benchmark_inspect", run_id=run.metadata.run_id) }}',
        benchmarkListUrl:    '{{ url_for("benchmark_list") }}'
      };
    </script>
    <script src="{{ url_for('serve_static', filename='benchmark_inspect.js') }}"></script>
{% endblock %}
```

#### 4c. Create `benchmarking/static/benchmark_inspect.js`

Move the JS from lines 1671-1833 (everything after the PAGE_DATA
assignments). Replace each Jinja2 expression with its `PAGE_DATA.*`
equivalent:

```js
// At the top of the file, read from PAGE_DATA
const photoResults = PAGE_DATA.photoResults;
const runId = PAGE_DATA.runId;
let currentIdx = PAGE_DATA.currentIdx;
let currentImageType = 'original';
let availableTabs = [];

// ... rest of code ...

// In updateDetails() (was line 1779):
//   Before: `{{ url_for('labels_index') }}${hashPrefix}?filter=all`
//   After:
document.getElementById('editLink').href = PAGE_DATA.editLinkBase + hashPrefix + '?filter=all';

// In updateImage() (was lines 1789-1794):
//   Before: `{{ url_for('serve_photo', content_hash='HASH') }}`.replace('HASH', hash)
//   After:
imagePath = PAGE_DATA.photoUrlTemplate.replace('HASH', hash);
//   Before: `{{ url_for('serve_artifact', run_id='RUN', ...) }}`.replace(...)
//   After:
imagePath = PAGE_DATA.artifactUrlTemplate
    .replace('RUN', runId)
    .replace('HASH', hashPrefix)
    .replace('TYPE', currentImageType);

// In applyFilter() (was line 1814):
//   Before: `{{ url_for('benchmark_inspect', run_id=run.metadata.run_id) }}?filter=${filter}`
//   After:
window.location.href = PAGE_DATA.inspectUrl + '?filter=' + filter;

// In changeRun() (was line 1819):
//   Before: `{{ url_for('benchmark_list') }}${newRunId}/`
//   After:
window.location.href = PAGE_DATA.benchmarkListUrl + newRunId + '/';
```

#### 4d. Change call site (lines 2410-2419):

```python
# Before
return render_template_string(
    BENCHMARK_INSPECT_TEMPLATE,
    run=run,
    filtered_results=filtered,
    current_idx=idx,
    filter=filter_type,
    photo_results_json=photo_results_json,
    all_runs=all_runs,
    pipeline_summary=pipeline_summary,
    passes_summary=passes_summary,
)
# After
return render_template(
    'benchmark_inspect.html',
    run=run,
    filtered_results=filtered,
    current_idx=idx,
    filter=filter_type,
    photo_results_json=photo_results_json,
    all_runs=all_runs,
    pipeline_summary=pipeline_summary,
    passes_summary=passes_summary,
)
```

**4e.** Delete the `BENCHMARK_INSPECT_TEMPLATE` constant (lines 1444-1837).

**4f.** Run `pytest tests/test_web_app.py`.

---

### Step 5 — `LABELING_TEMPLATE` → `templates/labeling.html` + `static/bib_labeling_ui.js`

**Source**: lines 271-689. Uses `COMMON_STYLES` (line 277).
Loads `labeling.js` at line 511. Inline `<script>` at lines 512-686
(175 lines).

**IMPORTANT**: The extracted template must preserve script load order:
1. `<script src="{{ url_for('serve_static', filename='labeling.js') }}">` (LabelingUI)
2. `<script>window.PAGE_DATA = { ... };</script>` (Jinja2 bridge)
3. `<script src="{{ url_for('serve_static', filename='bib_labeling_ui.js') }}">` (page logic)

#### 5a. Jinja2 expressions in the JS block

| JS line | Expression | PAGE_DATA key |
|---------|-----------|---------------|
| 513 | `'{{ split }}'` | `split` |
| 514 | `'{{ content_hash }}'` | `contentHash` |
| 614 | `'{{ url_for("save_label") }}'` | `saveUrl` |
| 633 | `{{ prev_url\|tojson }}` | `prevUrl` |
| 634 | `{{ next_url\|tojson }}` | `nextUrl` |
| 640 | `{{ next_unlabeled_url\|tojson }}` | `nextUnlabeledUrl` |
| 646 | `'{{ url_for("labels_index") }}'` | `labelsIndexUrl` |

#### 5b. Create the PAGE_DATA block in `templates/labeling.html`

```html
{% extends "base.html" %}
{% block title %}Labeling - {{ current }} / {{ total }}{% endblock %}
{% block extra_styles %}
        /* paste per-page CSS from lines 278-509 */
{% endblock %}
{% block body %}
    <!-- paste <body> contents from lines 333-509 -->

    <script src="{{ url_for('serve_static', filename='labeling.js') }}"></script>
    <script>
      window.PAGE_DATA = {
        split:            '{{ split }}',
        contentHash:      '{{ content_hash }}',
        saveUrl:          '{{ url_for("save_label") }}',
        prevUrl:          {{ prev_url|tojson }},
        nextUrl:          {{ next_url|tojson }},
        nextUnlabeledUrl: {{ next_unlabeled_url|tojson }},
        labelsIndexUrl:   '{{ url_for("labels_index") }}'
      };
    </script>
    <script src="{{ url_for('serve_static', filename='bib_labeling_ui.js') }}"></script>
{% endblock %}
```

#### 5c. Create `benchmarking/static/bib_labeling_ui.js`

Move lines 513-685. Replace Jinja2 with PAGE_DATA reads:

```js
let currentSplit = PAGE_DATA.split;
const contentHash = PAGE_DATA.contentHash;

// In save() (was line 614):
const response = await fetch(PAGE_DATA.saveUrl, { ... });

// In navigate() (was lines 633-634):
const prevUrl = PAGE_DATA.prevUrl;
const nextUrl = PAGE_DATA.nextUrl;

// In navigateUnlabeled() (was line 640):
const url = PAGE_DATA.nextUnlabeledUrl;

// In applyFilter() (was line 646):
window.location.href = PAGE_DATA.labelsIndexUrl + '?filter=' + newFilter;
```

The rest of the JS (functions `setSplit`, `getSelectedTags`, `showStatus`,
`renderBoxList`, `onBoxSelected`, keyboard handler, `startUI`) has **no
Jinja2** and can be copied verbatim.

#### 5d. Change call site (lines 1963-1979):

```python
return render_template(
    'labeling.html',
    content_hash=full_hash,
    bibs_str=', '.join(str(b) for b in label.bibs) if label else '',
    tags=label.tags if label else [],
    split=default_split,
    all_tags=sorted(ALLOWED_TAGS),
    current=idx + 1,
    total=total,
    has_prev=has_prev,
    has_next=has_next,
    prev_url=prev_url,
    next_url=next_url,
    next_unlabeled_url=next_unlabeled_url,
    filter=filter_type,
    latest_run_id=latest_run_id,
)
```

**5e.** Delete the `LABELING_TEMPLATE` constant (lines 271-689).

**5f.** Run `pytest tests/test_web_app.py`.

---

### Step 6 — `FACE_LABELING_TEMPLATE` → `templates/face_labeling.html` + `static/face_labeling_ui.js`

**Source**: lines 696-1302. Uses `COMMON_STYLES` (line 702).
Loads `labeling.js` at line 998. Inline `<script>` at lines 999-1299
(301 lines — the largest block).

Same script load order as step 5:
1. `labeling.js` (LabelingUI)
2. `PAGE_DATA` bridge
3. `face_labeling_ui.js`

#### 6a. Jinja2 expressions in the JS block

| JS line | Expression | PAGE_DATA key |
|---------|-----------|---------------|
| 1000 | `'{{ split }}'` | `split` |
| 1001 | `'{{ content_hash }}'` | `contentHash` |
| 1227 | `'{{ url_for("save_face_label") }}'` | `saveUrl` |
| 1246 | `{{ prev_url\|tojson }}` | `prevUrl` |
| 1247 | `{{ next_url\|tojson }}` | `nextUrl` |
| 1253 | `{{ next_unlabeled_url\|tojson }}` | `nextUnlabeledUrl` |
| 1259 | `'{{ url_for("face_labels_index") }}'` | `labelsIndexUrl` |

#### 6b. Hardcoded API paths (NOT Jinja2 — keep as-is in static JS)

These fetch calls use hardcoded paths, not `url_for()`. They will work in
static JS without PAGE_DATA. Document here for awareness — if routes ever
gain a URL prefix (e.g., Blueprint `url_prefix`), these would break.

| JS line | Hardcoded path | Purpose |
|---------|---------------|---------|
| 1025 | `fetch('/api/identities')` | Load identity autocomplete list |
| 1072 | `fetch('/api/face_identity_suggestions/' + contentHash + '?' + params)` | Embedding similarity suggestions |
| 1085 | `'/api/face_crop/' + s.content_hash + '/' + s.box_index` | Face crop thumbnail |
| 1207 | `fetch('/api/identities', { method: 'POST', ... })` | Auto-add new identities on save |

#### 6c. Create the PAGE_DATA block in `templates/face_labeling.html`

```html
{% extends "base.html" %}
{% block title %}Face Labeling - {{ current }} / {{ total }}{% endblock %}
{% block extra_styles %}
        /* paste per-page CSS from lines 703-996 */
{% endblock %}
{% block body %}
    <!-- paste <body> contents from lines 810-996 -->

    <script src="{{ url_for('serve_static', filename='labeling.js') }}"></script>
    <script>
      window.PAGE_DATA = {
        split:            '{{ split }}',
        contentHash:      '{{ content_hash }}',
        saveUrl:          '{{ url_for("save_face_label") }}',
        prevUrl:          {{ prev_url|tojson }},
        nextUrl:          {{ next_url|tojson }},
        nextUnlabeledUrl: {{ next_unlabeled_url|tojson }},
        labelsIndexUrl:   '{{ url_for("face_labels_index") }}'
      };
    </script>
    <script src="{{ url_for('serve_static', filename='face_labeling_ui.js') }}"></script>
{% endblock %}
```

#### 6d. Create `benchmarking/static/face_labeling_ui.js`

Move lines 1000-1298. Same PAGE_DATA substitution pattern as bib (step 5c).
Additionally, the 4 hardcoded `/api/` fetch calls stay as-is.

**Shared functions with `bib_labeling_ui.js`** (duplicated, intentionally):
- `setSplit()` — identical
- `showStatus()` — identical

Do NOT deduplicate in this task.

#### 6e. Change call site (lines 2081-2098):

```python
return render_template(
    'face_labeling.html',
    content_hash=full_hash,
    face_count=face_label.face_count if face_label else None,
    face_tags=face_label.tags if face_label else [],
    split=default_split,
    all_face_tags=sorted(ALLOWED_FACE_TAGS),
    face_box_tags=sorted(FACE_BOX_TAGS),
    current=idx + 1,
    total=total,
    has_prev=has_prev,
    has_next=has_next,
    prev_url=prev_url,
    next_url=next_url,
    next_unlabeled_url=next_unlabeled_url,
    filter=filter_type,
    latest_run_id=latest_run_id,
)
```

**6f.** Delete the `FACE_LABELING_TEMPLATE` constant (lines 696-1302).

**6g.** Run `pytest tests/test_web_app.py`.

---

### Step 7 — Final cleanup

**7a.** Remove the `COMMON_STYLES` constant (lines 67-178).

**7b.** Remove `render_template_string` from the flask import (line 25) —
no remaining callers.

**7c.** Do **NOT** rename `serve_static` → `static` or change
`url_for('serve_static', ...)` calls. That is deferred to task 005c.

**7d.** Run full `pytest` (all tests, not just web_app).

**7e.** Verify final file structure:

```
benchmarking/
  web_app.py                        ← ~800 lines (down from 2604)
  templates/
    base.html                       ← COMMON_STYLES CSS + block structure
    empty.html                      ← standalone (no base.html)
    labels_home.html                ← extends base.html
    benchmark_list.html             ← extends base.html
    benchmark_inspect.html          ← extends base.html + PAGE_DATA
    labeling.html                   ← extends base.html + PAGE_DATA
    face_labeling.html              ← extends base.html + PAGE_DATA
  static/
    labeling.js                     ← existing (unchanged)
    test_labeling.html              ← existing (unchanged)
    benchmark_inspect.js            ← new (168 lines)
    bib_labeling_ui.js              ← new (175 lines)
    face_labeling_ui.js             ← new (301 lines)
```

## Test strategy

- Run `pytest tests/test_web_app.py` after each step (31 API tests).
- Run full `pytest` after step 7 (all 245 tests).
- **Manual browser testing** after steps 4, 5, 6: load the page, verify
  navigation, saving, keyboard shortcuts, and canvas interaction all work.

## Scope boundaries

- **In scope**: template + JS extraction only.
- **Out of scope**: route changes, new features, CSS redesign, changing API
  contracts, modifying `LabelingCore` in `labeling.js`, renaming
  `serve_static`, deduplicating shared JS.
- **Do not** change how `create_app()` is called from `cli.py` or `bnr.py`.

## Risks and notes

- **`serve_static` vs Flask `static`**: The custom `serve_static` route
  (line 2467) shadows Flask's built-in `/static/` endpoint. All templates
  must use `url_for('serve_static', ...)`, NOT `url_for('static', ...)`.
  Switching is deferred to 005c.
- **Hardcoded `/api/` paths**: Face labeling JS has 4 hardcoded API URLs
  (documented in step 6b). These work fine now but would break if routes
  gain a URL prefix in 005b.
- **`photo_results_json | safe`**: Intentional bypass of Jinja2 escaping.
  Data is server-generated, not user input. Keep as-is.
- **Script load order matters**: `labeling.js` must load before
  `bib_labeling_ui.js` / `face_labeling_ui.js` because they reference
  `LabelingUI` which is defined in `labeling.js`.
- **Shared duplicated code**: `setSplit()` and `showStatus()` are identical
  in bib and face JS files. Intentional — do not deduplicate in this task.
