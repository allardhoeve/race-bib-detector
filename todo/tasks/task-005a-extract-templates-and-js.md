# Task 005a: Extract templates and inline JS from web_app.py

Part 1 of 3 — see also [005b](task-005b-blueprint-route-split.md), [005c](task-005c-extract-helpers-cleanup.md).

## Goal

Move all inline HTML templates and inline `<script>` blocks out of
`benchmarking/web_app.py` into Jinja2 template files and static JS files.
Pure extraction — no behavior changes.

## Background

`web_app.py` is 2604 lines. ~1800 of those are inline template strings and
inline JS. Extracting them shrinks the Python file to ~800 lines and makes
templates editable with proper syntax highlighting.

## Approach

Work **one template at a time**, in order of complexity. Run
`pytest tests/test_web_app.py` after each.

### Setup

1. Create `benchmarking/templates/` directory.
2. Create `benchmarking/templates/base.html` with the `COMMON_STYLES` CSS in a
   `<style>` block. Other templates will `{% extends "base.html" %}`.
3. Set `template_folder=...` in the Flask app constructor in `create_app()`.
4. Add `render_template` to imports, alongside (not replacing yet)
   `render_template_string`.

### Template extraction order

Each step: move template string → `.html` file, switch `render_template_string`
→ `render_template`, delete the Python string constant.

| Order | Template constant | Target file | Has inline JS? |
|-------|-------------------|-------------|----------------|
| 1 | `EMPTY_TEMPLATE` | `empty.html` | No |
| 2 | `LABELS_HOME_TEMPLATE` | `labels_home.html` | No |
| 3 | `BENCHMARK_LIST_TEMPLATE` | `benchmark_list.html` | No |
| 4 | `BENCHMARK_INSPECT_TEMPLATE` | `benchmark_inspect.html` | Yes — extract to `static/benchmark_inspect.js` |
| 5 | `LABELING_TEMPLATE` | `labeling.html` | Yes — extract to `static/bib_labeling_ui.js` |
| 6 | `FACE_LABELING_TEMPLATE` | `face_labeling.html` | Yes — extract to `static/face_labeling_ui.js` |

### Inline JS extraction pattern (steps 4-6)

The inline `<script>` blocks contain Jinja2 expressions (`{{ content_hash }}`,
`{{ url_for(...) }}`, etc.). Static `.js` files can't use Jinja2. Use a
`PAGE_DATA` bridge:

**In the `.html` template** (Jinja2 renders this):
```html
<script>
  window.PAGE_DATA = {
    contentHash: '{{ content_hash }}',
    split: '{{ split }}',
    saveUrl: '{{ url_for("save_label") }}',
    prevUrl: {{ prev_url|tojson }},
    nextUrl: {{ next_url|tojson }},
    nextUnlabeledUrl: {{ next_unlabeled_url|tojson }},
    labelsIndexUrl: '{{ url_for("labels_index") }}'
  };
</script>
<script src="{{ url_for('static', filename='bib_labeling_ui.js') }}"></script>
```

**In the static `.js` file**: read from `PAGE_DATA.*` instead of the old
Jinja2 expressions.

#### Jinja2 variables per script

**bib_labeling_ui.js** — `split`, `content_hash`, `url_for('save_label')`,
`prev_url`, `next_url`, `next_unlabeled_url`, `url_for('labels_index')`

**face_labeling_ui.js** — `split`, `content_hash`,
`url_for('save_face_label')`, `prev_url`, `next_url`, `next_unlabeled_url`,
`url_for('face_labels_index')`

**benchmark_inspect.js** — `photo_results_json`, `run.metadata.run_id`,
`current_idx`, `url_for('labels_index')`, `url_for('serve_photo', ...)`,
`url_for('serve_artifact', ...)`, `url_for('benchmark_inspect', ...)`,
`url_for('benchmark_list')`

### Final cleanup

- Remove `render_template_string` import (no longer used).
- Remove `COMMON_STYLES` constant.
- Verify `url_for('serve_static', ...)` references in templates change to
  `url_for('static', ...)` (Flask built-in static serving — see task 005c).

## Test strategy

- Run `pytest tests/test_web_app.py` after each template extraction (33 tests).
- Run full `pytest` after all 6 are done.

## Scope boundaries

- **In scope**: template + JS extraction only.
- **Out of scope**: route changes, new features, CSS redesign, changing API
  contracts, modifying `LabelingCore` in `labeling.js`.
- **Do not** change how `create_app()` is called from `cli.py` or `bnr.py`.
