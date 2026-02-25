# Task 011: Deduplicate shared labeling JS helpers

Small cleanup. Independent of all other pending tasks.

## Goal

`setSplit()` and `showStatus()` are duplicated verbatim between `bib_labeling_ui.js`
and `face_labeling_ui.js`. Move them into `labeling.js` (which both pages already load
before the page-specific files).

## Current duplication

Both `bib_labeling_ui.js` (lines 4–22) and `face_labeling_ui.js` (lines 4–22) contain:

```js
function setSplit(split) {
    currentSplit = split;
    document.querySelectorAll('.split-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase() === split);
    });
}

function showStatus(message, isError) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status ' + (isError ? 'error' : 'success');
    status.style.display = 'block';
    setTimeout(() => { status.style.display = 'none'; }, 2000);
}
```

These are page-level globals (not inside any class/namespace) and have no
dependency on `LabelingUI` or `LabelingCore`. They only use standard DOM APIs.

## Script load order (verify before editing)

Both `labeling.html` and `face_labeling.html` load scripts in this order:

1. `labeling.js` ← add functions here
2. `<script>window.PAGE_DATA = {...}</script>`
3. `bib_labeling_ui.js` / `face_labeling_ui.js` ← remove functions from here

This order guarantees `setSplit` and `showStatus` are defined before the
page-specific files reference them.

## Changes

### 1. Add to `benchmarking/static/labeling.js`

Append after the closing `})();` of the `LabelingUI` IIFE (end of file):

```js
// =============================================================================
// Shared page helpers (used by bib_labeling_ui.js and face_labeling_ui.js)
// =============================================================================

function setSplit(split) {
    // currentSplit is a variable in each page-specific file.
    // This function only updates the button UI; the caller updates currentSplit.
    document.querySelectorAll('.split-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase() === split);
    });
}

function showStatus(message, isError) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = 'status ' + (isError ? 'error' : 'success');
    status.style.display = 'block';
    setTimeout(() => { status.style.display = 'none'; }, 2000);
}
```

**Note on `setSplit`**: the original also sets `currentSplit = split`, but
`currentSplit` is declared in each page-specific file. Options:

a) Keep `currentSplit = split` in each file's `setSplit` caller: each page-specific
   file calls the shared `setSplit(split)` for UI only, and sets `currentSplit`
   separately. This is cleaner.

b) Pass `currentSplit` as a parameter (more invasive).

**Recommended approach (a)**: in each page-specific file, replace:
```js
function setSplit(split) {        // ← remove this entire function
    currentSplit = split;
    document.querySelectorAll(...
}
```
with inline `currentSplit = split;` at each call site. There is exactly one call
site in each file (the `setSplit` button `onclick`). Update the HTML buttons
to call something like `onSplitClick('iteration')`:

```js
// In bib_labeling_ui.js, add:
function onSplitClick(split) {
    currentSplit = split;
    setSplit(split);   // shared function in labeling.js
}
```

And update the template button `onclick` from `setSplit('iteration')` to
`onSplitClick('iteration')`. Check both `labeling.html` and `face_labeling.html`
for the split button click handlers.

### 2. Remove from `benchmarking/static/bib_labeling_ui.js`

Delete lines 4–22 (the `setSplit` and `showStatus` function definitions).
Replace call sites as described above.

### 3. Remove from `benchmarking/static/face_labeling_ui.js`

Delete lines 4–22 (same functions). Replace call sites identically.

## Verification

- Run `pytest tests/test_web_app.py` — API tests should pass unchanged.
- Manual browser testing:
  - Open `/labels/` — click split buttons, verify they highlight correctly.
  - Save a bib label — verify "Saved!" status message appears.
  - Open `/faces/labels/` — verify same behavior.
  - Check browser console for JS errors.

## Scope boundaries

- **In scope**: moving two functions to `labeling.js`, updating call sites.
- **Out of scope**: changes to `LabelingCore`, `LabelingUI`, API endpoints, templates
  beyond split button onclick handlers.
- **Do not** rename the functions (`setSplit`, `showStatus`) — they may be referenced
  by the browser integration test at `/test/labeling`.
