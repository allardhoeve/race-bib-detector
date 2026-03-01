# Task 053: Canvas overlay on inspect page for bib/face boxes

Depends on task-052.

## Goal

Add an interactive canvas overlay to the benchmark inspect page that draws predicted and ground-truth bounding boxes over the photo, with colour-coding by type (bib vs face) and match status (TP/FP/FN).

## Background

After tasks 049-052, the inspect page JSON contains per-photo bib and face boxes (both predictions and GT) with normalised [0,1] coordinates. This task renders them visually so the user can see at a glance where detection succeeded or failed — without switching to the labeling UI.

## Context

- `benchmarking/templates/benchmark_inspect.html` — inspect template with photo display area
- `benchmarking/static/labeling.js` — existing `LabelingCore` has box rendering logic (reusable patterns but different context)
- `benchmarking/scoring.py` — IoU matching logic (`_match_boxes`, `iou_single`); could be reimplemented in JS or pre-computed server-side
- `benchmarking/ground_truth.py` — `BibBox` / `FaceBox` field reference
- Box coordinates are normalised [0,1] — multiply by displayed image width/height for canvas pixels

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Rendering tech | HTML5 Canvas overlay, positioned absolutely over the `<img>` element |
| Box matching (TP/FP/FN) | Pre-compute server-side in task-052 route, OR compute client-side via IoU. Start with client-side IoU for simplicity |
| Colour scheme | GT bib: blue dashed. Pred bib TP: green solid. Pred bib FP: red solid. FN: blue dashed (no matching pred). GT face: purple dashed. Pred face TP: teal solid. Pred face FP: orange solid |
| Toggle controls | Checkboxes: "Show bib boxes", "Show face boxes", "Show GT", "Show predictions". All on by default |
| Labels on boxes | Bib: show number string. Face: show identity (from GT) or cluster_id (from pred). Scope shown as small tag |
| Link lines | If `gt_links` present, draw thin lines connecting linked bib↔face GT pairs |
| Resize handling | Recalculate on window resize and image load; use ResizeObserver on image container |

## Changes

### Modified: `benchmarking/templates/benchmark_inspect.html`

Add canvas overlay and toggle controls to the photo display area:

```html
<!-- After the existing photo img element -->
<div id="overlay-container" style="position: relative; display: inline-block;">
  <img id="photo-img" src="..." style="display: block; max-width: 100%;">
  <canvas id="box-overlay" style="position: absolute; top: 0; left: 0; pointer-events: none;"></canvas>
</div>

<!-- Toggle controls -->
<div id="overlay-controls" class="mb-2">
  <label><input type="checkbox" id="show-bib-boxes" checked> Bib boxes</label>
  <label><input type="checkbox" id="show-face-boxes" checked> Face boxes</label>
  <label><input type="checkbox" id="show-gt" checked> Ground truth</label>
  <label><input type="checkbox" id="show-pred" checked> Predictions</label>
  <label><input type="checkbox" id="show-links" checked> Links</label>
</div>
```

### New: `benchmarking/static/inspect_overlay.js`

Client-side rendering logic:

```javascript
// inspect_overlay.js — Canvas overlay for benchmark inspect page

class InspectOverlay {
  constructor(imgEl, canvasEl, photoData) {
    this.img = imgEl;
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext('2d');
    this.photoData = photoData;
    this.options = {
      showBibBoxes: true,
      showFaceBoxes: true,
      showGT: true,
      showPred: true,
      showLinks: true,
    };
    this._setupResize();
  }

  _setupResize() {
    const ro = new ResizeObserver(() => this.draw());
    ro.observe(this.img);
    this.img.addEventListener('load', () => this.draw());
  }

  draw() {
    const w = this.img.clientWidth;
    const h = this.img.clientHeight;
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx.clearRect(0, 0, w, h);

    const data = this.photoData;
    if (!data) return;

    // Draw GT boxes (dashed)
    if (this.options.showGT) {
      if (this.options.showBibBoxes && data.gt_bib_boxes) {
        this._drawBoxes(data.gt_bib_boxes, w, h, '#3b82f6', true, 'bib');
      }
      if (this.options.showFaceBoxes && data.gt_face_boxes) {
        this._drawBoxes(data.gt_face_boxes, w, h, '#8b5cf6', true, 'face');
      }
    }

    // Draw prediction boxes (solid)
    if (this.options.showPred) {
      if (this.options.showBibBoxes && data.pred_bib_boxes) {
        // Color by match status (simplified: green if number in expected, red otherwise)
        for (const box of data.pred_bib_boxes) {
          const isTP = data.expected_bibs.includes(parseInt(box.number));
          const color = isTP ? '#22c55e' : '#ef4444';
          this._drawBox(box, w, h, color, false, box.number);
        }
      }
      if (this.options.showFaceBoxes && data.pred_face_boxes) {
        this._drawBoxes(data.pred_face_boxes, w, h, '#14b8a6', false, 'face');
      }
    }

    // Draw link lines
    if (this.options.showLinks && data.gt_links && data.gt_bib_boxes && data.gt_face_boxes) {
      this._drawLinks(data.gt_links, data.gt_bib_boxes, data.gt_face_boxes, w, h);
    }
  }

  _drawBoxes(boxes, imgW, imgH, color, dashed, type) { /* ... */ }
  _drawBox(box, imgW, imgH, color, dashed, label) { /* ... */ }
  _drawLinks(links, bibBoxes, faceBoxes, imgW, imgH) { /* ... */ }
}
```

Key rendering logic per box:

```javascript
_drawBox(box, imgW, imgH, color, dashed, label) {
  const ctx = this.ctx;
  const x = box.x * imgW;
  const y = box.y * imgH;
  const w = box.w * imgW;
  const h = box.h * imgH;

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash(dashed ? [6, 3] : []);
  ctx.strokeRect(x, y, w, h);

  if (label) {
    ctx.font = '12px monospace';
    ctx.fillStyle = color;
    ctx.fillRect(x, y - 16, ctx.measureText(label).width + 4, 16);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, x + 2, y - 4);
  }
  ctx.setLineDash([]);
}
```

## Tests

No Python tests needed (pure JS). Manual verification:

- Open inspect page for a run with box data
- Verify bib GT boxes appear as blue dashed rectangles
- Verify predicted bib boxes appear green (TP) or red (FP)
- Verify face boxes appear when face detection was enabled
- Verify toggles show/hide each category
- Verify canvas resizes correctly with window

Optional: add a simple pytest test that the template includes the `inspect_overlay.js` script tag.

## Verification

```bash
# Run benchmark with face detection
venv/bin/python bnr.py benchmark run -s iteration

# Start UI
venv/bin/python bnr.py benchmark ui

# Open inspect page in browser, navigate to a photo with boxes
# Toggle checkboxes to verify overlay controls work
```

## Pitfalls

- Canvas must resize when the image loads (natural dimensions may differ from initial layout). Use both `ResizeObserver` and `img.onload`.
- Normalised coordinates assume the image is displayed at its natural aspect ratio. If CSS constrains width (e.g. `max-width: 100%`), the canvas must match the *displayed* size, not the natural size.
- The overlay canvas must have `pointer-events: none` so clicks pass through to the image (for navigation, right-click save, etc.).
- Old runs without box data: JS should check for field presence before drawing. No errors on missing data.

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] Canvas overlay renders over inspect page photo
- [ ] GT bib boxes drawn as blue dashed rectangles with number labels
- [ ] Predicted bib boxes drawn as green (TP) or red (FP) solid rectangles
- [ ] Face boxes drawn when face detection data is present
- [ ] Toggle checkboxes control visibility of each box category
- [ ] Link lines connect linked bib↔face GT pairs
- [ ] Overlay resizes correctly when window resizes
- [ ] Old runs (without box data) show no overlay, no JS errors

## Scope boundaries

- **In scope**: canvas overlay, toggle controls, colour-coded box rendering, link lines
- **Out of scope**: editing boxes from inspect page, IoU threshold controls, face cluster colouring (enhancement on top of task-051)
- **Do not** modify detection logic, scoring, or labeling UI
