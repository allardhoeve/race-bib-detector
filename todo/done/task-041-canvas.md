# Task 038: Extract PhotoCanvas component; fix scope-aware colours in associations view

Independent of other open tasks.

## Goal

Extract a `PhotoCanvas` component from `LabelingUI` in `labeling.js` so that all three
labeling views (bib, face, associations) share the same canvas plumbing and scope-aware
box colouring.  The immediate visible bug is that excluded faces are shown blue instead of
red in the associations view; the same defect affects bib-scope colours there too.

## Background

The bib and face labeling views both delegate to `LabelingUI` (mode='bib' / mode='face'),
which owns `BOX_COLORS`, `drawBox()`, `getImageRect()`, the resize observer, etc.  The
associations view (`link_labeling_ui.js`) was written independently and duplicates all of
that infrastructure, but hardcodes colours instead of reading `box.scope`.

Confirmed bug on `/associations/2a693f17`: 3 of 4 face boxes have `scope: "exclude"` but
are all drawn blue.  Bib boxes are all drawn orange regardless of scope (`not_bib`,
`bib_obscured`, `bib_clipped` distinctions lost).

## Context

`labeling.js` already has a clean split:
- `LabelingCore` — pure logic, no DOM (coordinate math, hit testing, IoU)
- `LabelingUI` — DOM/canvas interaction, wraps `LabelingCore`

`PhotoCanvas` fits as a third layer between them: shared canvas infrastructure without
edit interactions.

### Code currently duplicated in `link_labeling_ui.js`

| Duplicated item | Canonical location | Lines in link_labeling_ui.js |
|-----------------|--------------------|------------------------------|
| `getImageRect()` | `LabelingUI` (line 227) | 30–40 (identical) |
| `canvasPos()` | `LabelingUI.getCanvasPos()` | 46–49 (identical) |
| `resizeCanvas()` + ResizeObserver | `LabelingUI` (line 568) | 296–304 |
| Bib box drawing loop | `LabelingUI.drawBox()` | 72–88 (no scope colours) |
| Face box drawing loop | `LabelingUI.drawBox()` | 92–108 (hardcoded blue) |

`BOX_COLORS` lives inside the `LabelingUI` IIFE closure and is not accessible outside it.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where does `BOX_COLORS` live? | Promote to `LabelingCore` — pure data, no DOM dependency. Accessible to both `LabelingUI` and `link_labeling_ui.js`. |
| New component name | `PhotoCanvas` — IIFE in `labeling.js`, between `LabelingCore` and `LabelingUI`. |
| Does `LabelingUI` change its public API? | No. It wraps `PhotoCanvas` internally. `init()`, `getState()`, `render()`, etc. stay the same. |
| Does associations view use `LabelingUI`? | No. `LabelingUI` manages one box set (bib *or* face). Associations needs both simultaneously plus link-line drawing. `link_labeling_ui.js` uses `PhotoCanvas` directly and keeps its own click-to-link interaction. |
| Template CSS duplication? | Out of scope for this task. |

## Changes: `benchmarking/static/labeling.js`

### Move `BOX_COLORS` into `LabelingCore`

```js
// Inside LabelingCore IIFE, before the return statement:
var BOX_COLORS = {
    bib: '#00ff88',
    not_bib: '#ff4444',
    bib_obscured: '#ffaa00',
    bib_clipped: '#88ccff',
    keep: '#00aaff',
    exclude: '#ff4444',
    uncertain: '#888888',
};

// Add to LabelingCore return object:
BOX_COLORS: BOX_COLORS,
```

Remove `BOX_COLORS` from `LabelingUI` and replace the one reference with `C.BOX_COLORS`.

### New: `PhotoCanvas` IIFE (insert between `LabelingCore` and `LabelingUI`)

```js
var PhotoCanvas = (function () {
    'use strict';
    var C = LabelingCore;

    function create(opts) {
        // opts: { imgEl, canvasEl }
        var imgEl = opts.imgEl;
        var canvasEl = opts.canvasEl;
        var ctx = canvasEl.getContext('2d');

        function getImageRect() { /* same logic as LabelingUI.getImageRect */ }

        function clear() {
            ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        }

        function drawBox(box, mode, isSelected) {
            var imgRect = getImageRect();
            var r = C.boxToCanvasRect(box, imgRect);
            var colorKey = box.scope || (mode === 'bib' ? 'bib' : 'keep');
            var color = C.BOX_COLORS[colorKey] || '#00ff88';
            // ... stroke, label, handles (same as current LabelingUI.drawBox)
        }

        function drawLinkLine(bibBox, faceBox) {
            var imgRect = getImageRect();
            // ... draw line between box centres
        }

        function resizeCanvas() {
            canvasEl.width = canvasEl.parentElement.clientWidth;
            canvasEl.height = canvasEl.parentElement.clientHeight;
        }

        function startResizeObserver(onResize) {
            var ro = new ResizeObserver(function () { resizeCanvas(); onResize(); });
            ro.observe(canvasEl.parentElement);
        }

        return { getImageRect, clear, drawBox, drawLinkLine, resizeCanvas, startResizeObserver, ctx };
    }

    return { create: create };
})();
```

### Modified: `LabelingUI`

- Remove `getImageRect()` — delegate to `_canvas.getImageRect()`
- Remove `drawBox()` — delegate to `_canvas.drawBox(box, state.mode, isSelected)`
- Remove `drawSuggestion()` stub — keep as-is or delegate
- Remove `resizeCanvas()` / ResizeObserver setup — delegate to `_canvas`
- `init()` calls `_canvas = PhotoCanvas.create({ imgEl, canvasEl })` first

Public API of `LabelingUI` is unchanged.

## Changes: `benchmarking/static/link_labeling_ui.js`

Replace the entire rendering + canvas-setup section with `PhotoCanvas`:

```js
var _canvas = PhotoCanvas.create({ imgEl: img, canvasEl: canvas });

function redraw() {
    _canvas.clear();
    bibBoxes.forEach(function (b, i) {
        _canvas.drawBox(b, 'bib', i === selectedBibIdx);
    });
    faceBoxes.forEach(function (b) {
        _canvas.drawBox(b, 'face', false);
    });
    links.forEach(function (lnk) {
        var bb = bibBoxes[lnk[0]], fb = faceBoxes[lnk[1]];
        if (bb && fb) _canvas.drawLinkLine(bb, fb);
    });
}

_canvas.startResizeObserver(redraw);
```

Remove: `getImageRect()`, `canvasPos()` (keep local for click handling),
`boxCenter()` (move into `PhotoCanvas.drawLinkLine`), the bib/face drawing loops,
the ResizeObserver block.

`canvasPos()` stays local since it's only used for click hit-testing, not rendering.

## Tests

No new automated tests needed — rendering is visual.  Existing 250 tests should still
pass (no Python changes; no changes to `LabelingCore` public API).

Manual verification:
- `/associations/2a693f17`: excluded face boxes should now render red, one `keep` box blue
- Check a photo with `not_bib` or `bib_obscured` boxes in associations view — correct colours
- Bib labeling view unchanged (LabelingUI public API preserved)
- Face labeling view unchanged

## Scope boundaries

- **In scope**: `labeling.js` (LabelingCore + new PhotoCanvas + LabelingUI refactor), `link_labeling_ui.js`
- **Out of scope**: Template HTML/CSS duplication, Python routes, test files, `bib_labeling_ui.js` / `face_labeling_ui.js` (they call `LabelingUI` which is unchanged externally)
- **Do not** change the public API of `LabelingUI` (`init`, `getState`, `render`, `selectBox`, `deleteSelected`, `fetchBoxes`, `resizeCanvas`)
