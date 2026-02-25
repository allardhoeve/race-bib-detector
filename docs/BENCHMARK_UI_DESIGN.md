# Benchmark Labeling UI Design

This document captures the conventions, layout patterns, and design decisions for the
benchmark labeling web UI. Follow these conventions when adding new pages or modifying
existing ones.

`BENCHMARK_DESIGN.md` covers the ground truth schema and pipeline design.
`STANDARDS.md` covers project-wide coding conventions.

---

## Layout

Every per-photo labeling page uses a three-zone layout:

```
┌─────────────────────────────────────────────────────────────┐
│  header: ← back links │ prev/next │ counter │ filter        │
├──────────────────────────────────────┬──────────────────────┤
│                                      │                       │
│   image-panel (fills remaining       │   form-panel          │
│   width; canvas overlay on photo)    │   right sidebar       │
│                                      │   fixed width,        │
│                                      │   scrollable          │
└──────────────────────────────────────┴──────────────────────┘
```

- **image-panel**: `flex: 1`, contains `<img>` + `<canvas>` in `object-fit: contain` layout.
  Canvas is absolutely positioned to fill the container; resized via `ResizeObserver`.
- **form-panel**: fixed width (350 px bib, 300 px face/links), `overflow-y: auto`.

The `base.html` skeleton provides the outer `<body>` flex column; pages extend it via
`{% block body %}`.

---

## Navigation

### Prev / Next buttons

All labeling pages pass three navigation URLs from the route to the template:

| Variable | Meaning |
|---|---|
| `prev_url` | URL of the previous photo in the current filtered list |
| `next_url` | URL of the next photo in the current filtered list |
| `next_unlabeled_url` | URL of the next photo **not yet processed** in this dimension |

These are injected into `window.PAGE_DATA` and consumed by the shared helpers in
`labeling.js`:

```js
function navigate(direction) { /* uses PAGE_DATA.prevUrl / nextUrl */ }
function navigateUnlabeled()  { /* uses PAGE_DATA.nextUnlabeledUrl */ }
```

**Convention:** every per-photo labeling page **must** provide all three URLs.
`next_unlabeled_url` may be `null` when all photos are processed, in which case the
"Next unlabeled" button is hidden (not disabled).

### "Next unprocessed" button

Every labeling section **must** show a "Next unlabeled →→" button whenever
`next_unlabeled_url` is available. This is the primary workflow accelerator.
"Unlabeled" means different things per section:

| Section | "Unprocessed" definition |
|---|---|
| Bib | `bib_label.labeled == False` |
| Face | `is_face_labeled(label) == False` (no boxes and no tags) |
| Links | `content_hash not in link_gt.photos` |

### Cross-section links (same photo)

The header of each labeling page must contain links to the **other two labeling sections
for the same photo**. The link must use the same `content_hash` (8-char prefix), so the
operator can jump between sections without losing their place.

Current cross-links:

| Page | Header links to |
|---|---|
| Bib (`/labels/<hash>`) | Face Labels, Links |
| Face (`/faces/labels/<hash>`) | Bib Labels, Links |
| Links (`/links/<hash>`) | Bib Labels, Face Labels |

### Filter

Sections that have a list view (bib, face) show a filter dropdown: `All / Unlabeled /
Labeled`. The current filter is carried in the `?filter=` URL parameter.
`applyFilter()` in `labeling.js` handles the redirect.

---

## Keyboard Shortcuts

### Shared (all labeling pages)

Defined in `labeling.js` via `LabelingUI.onKeyDown` (canvas) and per-page `keydown`
listeners:

| Key | Action |
|---|---|
| `←` / `→` | Navigate to previous / next photo |
| `Enter` | Save and advance to next photo |
| `Delete` / `Backspace` | Delete the currently selected box |
| `Tab` | Accept the next unreviewed suggestion box |
| `Escape` | Deselect the current box |

### Bib-specific

Defined in `bib_labeling_ui.js`:

| Key | Action |
|---|---|
| `O` | Toggle `obscured_bib` photo tag |
| `N` | Toggle `no_bib` photo tag |
| `B` | Toggle `blurry_bib` photo tag |

### Face-specific

Defined in `face_labeling_ui.js`:

| Key | Action |
|---|---|
| `N` | Toggle `no_faces` photo tag |
| `L` | Toggle `light_faces` photo tag |

### Link-specific

Defined in `link_labeling_ui.js`:

| Key | Action |
|---|---|
| `N` | Mark photo as "No Links" (saves empty link list) |

### Convention for new pages

When adding a new labeling page:
1. Add navigation shortcuts (`←` / `→`) unconditionally.
2. Add `Enter` for save if the page has a save action.
3. Document all page-specific shortcuts in the `keyboard-hint` div at the bottom of
   the form panel (visible to the operator at a glance).
4. Add the shortcuts to this file.

Keyboard listeners must guard against misfires while the operator is typing in an
`<input>`, `<select>`, or `<textarea>`:
```js
if (e.target.tagName === 'INPUT' || ...) return;
```

---

## PAGE_DATA Convention

All per-photo labeling pages inject server-side data into `window.PAGE_DATA` via an
inline `<script>` block (or a `<script id="page-data" type="application/json">` block
for complex payloads). Page-specific JS reads only from this object — no inline Jinja
expressions in JS logic.

Required fields:

| Field | Type | Description |
|---|---|---|
| `content_hash` | string | Full 64-char SHA-256 hash |
| `prevUrl` | string \| null | URL of previous photo |
| `nextUrl` | string \| null | URL of next photo |
| `nextUnlabeledUrl` | string \| null | URL of next unprocessed photo |

The bib and face pages also include `split`, `saveUrl`, and `labelsIndexUrl`.
The links page includes `bib_boxes`, `face_boxes`, `links`, `is_processed`.

---

## Status Messages

`showStatus(message, isError)` in `labeling.js` shows a transient notification in the
`#status` div. It auto-hides after 2 seconds.

- Success: `background: #0f3460; color: #0f9b0f` (dark blue / green text)
- Error: `background: #3d0a0a; color: #ff6b6b` (dark red / red text)

Every labeling page must include a `<div id="status" class="status" style="display: none;"></div>`.

---

## Canvas and Box Colours

Box colours are scope-keyed, defined in `LabelingUI` (`labeling.js`):

| Scope | Colour | Description |
|---|---|---|
| `bib` | `#00ff88` | Confirmed bib (green) |
| `not_bib` | `#ff4444` | False positive region (red) |
| `bib_obscured` | `#ffaa00` | Obscured bib (orange) |
| `bib_clipped` | `#88ccff` | Clipped bib (light blue) |
| `keep` (face) | `#00aaff` | Face to recognise (blue) |
| `exclude` (face) | `#ff4444` | Ignored face (red) |
| `uncertain` (face) | `#888888` | Uncertain face (grey) |

On the link page (read-only, separate renderer in `link_labeling_ui.js`):

| Element | Colour |
|---|---|
| Bib box | `rgba(255, 140, 0, 0.9)` orange; yellow when selected |
| Face box | `rgba(60, 120, 255, 0.85)` blue |
| Link line | `rgba(160, 160, 160, 0.7)` grey |

Suggestion boxes use a dashed `rgba(255, 255, 100, 0.6)` yellow outline.

---

## Link Labeling Page: Access Control

The link labeling page (`/links/<hash>`) is only meaningful for photos that have been
labeled in both the bib and face dimensions.

**Qualifying condition:** `bib_labeled == True AND face_labeled == True`
(i.e. the bib `labeled` flag is set, and `is_face_labeled()` returns True — boxes or
tags are present on the face label).

- Photos with 0 bib boxes or 0 face boxes **are still included** so the operator can
  catch labeling errors. The completeness module handles the trivially-N/A case
  separately (no link step required when either count is 0).
- Navigating directly to a non-qualifying photo renders a **soft info page** explaining
  why linking is not possible and offering a direct link to the unfinished bib or face
  labeling page for that photo. No hard redirect; no 404.
- The `/links/` index redirects to the first qualifying photo.
- "Next unlabeled" skips to the next photo in `link_gt.photos` that is not yet
  processed, among qualifying photos only.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Navigation defined centrally | `navigate()` / `navigateUnlabeled()` in `labeling.js` | Avoid copy-paste across three page JS files |
| Keyboard shortcuts per page | Defined in each page's JS file | Page-specific shortcuts differ; central file would require mode flags |
| Cross-section links anchor to same hash | `content_hash[:8]` passed in header links | Operator stays on the same photo when switching between bib/face/link labeling |
| "Next unlabeled" on every page | Required convention | Workflow accelerator; avoids operators reviewing already-done photos |
| Link page filter: bib_labeled AND face_labeled | Threshold 1a | Photos with 0 boxes are still shown so operators can catch errors; trivial N/A is handled by completeness module, not by hiding photos |
| Non-qualifying link page visit: soft info | Soft info page, not redirect or 404 | Redirect silently loses context; 404 is confusing for a valid photo hash |
| PAGE_DATA injected server-side | Inline JSON block in template | No extra API round-trip on page load; Jinja templating stays out of JS logic |
