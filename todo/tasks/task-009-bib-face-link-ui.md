# Task 009: Bib-face link UI

Step 5 (part 3/4). Depends on task-008 (API routes).

## User workflow

1. User labels bib boxes on `/labels/<hash>` (done).
2. User labels face boxes on `/faces/<hash>` (done).
3. User navigates to `/links/<hash>` — a new, dedicated page.
   - Both sets of already-labeled boxes are shown on the photo (read-only).
   - The user clicks a bib box to select it as the link source (highlights yellow).
   - The user clicks a face box to complete the link; a line appears between the two.
   - Clicking the same pair again removes the link (toggle).
   - Links are saved automatically.

No box editing happens on the link page. The boxes are static display only.

## New route: `GET /links/<content_hash>`

Add to `benchmarking/routes_bib.py` (the bib Blueprint already owns link management):

```python
@bib_bp.route('/links/<content_hash>')
def link_photo(content_hash):
    """Link labeling page: associate bib boxes with face boxes."""
    from benchmarking.ground_truth import (
        load_bib_ground_truth, load_face_ground_truth, load_link_ground_truth,
    )
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return "Photo not found", 404

    photo_paths = index[full_hash]
    photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths

    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    bib_label = bib_gt.get_photo(full_hash)
    face_label = face_gt.get_photo(full_hash)
    link_label = link_gt.get_links(full_hash)

    bib_boxes = [b.to_dict() for b in bib_label.boxes] if bib_label else []
    face_boxes = [b.to_dict() for b in face_label.boxes] if face_label else []
    links = [lnk.to_pair() for lnk in link_label]

    # Prev/next navigation across all photos
    all_hashes = sorted(index.keys())
    try:
        idx = all_hashes.index(full_hash)
    except ValueError:
        return "Photo not in index", 404

    total = len(all_hashes)
    prev_url = url_for('bib.link_photo', content_hash=all_hashes[idx - 1][:8]) if idx > 0 else None
    next_url = url_for('bib.link_photo', content_hash=all_hashes[idx + 1][:8]) if idx < total - 1 else None

    return render_template(
        'link_labeling.html',
        content_hash=full_hash,
        photo_path=photo_path,
        bib_boxes=bib_boxes,
        face_boxes=face_boxes,
        links=links,
        current=idx + 1,
        total=total,
        prev_url=prev_url,
        next_url=next_url,
    )
```

## New template: `benchmarking/templates/link_labeling.html`

Extends `base.html`. Layout mirrors `labeling.html` and `face_labeling.html`:
photo canvas on the left, sidebar on the right.

- Sidebar shows:
  - Navigation (prev / next, `current / total`)
  - Bib box count and face box count (informational)
  - Link count (updates live as links are created/removed)
  - Instructions: "Click a bib box, then a face box to link them. Click again to unlink."
- Canvas: photo image with bib boxes, face boxes, and link lines drawn on top.
- PAGE_DATA block passes `content_hash`, `bib_boxes`, `face_boxes`, `links` as JSON.

No form submission — all saves go through the JS API call.

## New JS file: `benchmarking/static/link_labeling_ui.js`

The link page does **not** use `LabelingUI` for interaction (no box editing). It uses
`LabelingCore` for coordinate utilities only (`boxToCanvasRect`, `hitTestBox`,
`normalToCanvas`).

### State

```js
const PAGE_DATA = JSON.parse(document.getElementById('page-data').textContent);
const contentHash = PAGE_DATA.content_hash;

let bibBoxes = PAGE_DATA.bib_boxes;
let faceBoxes = PAGE_DATA.face_boxes;
let links = PAGE_DATA.links;          // [[bib_idx, face_idx], ...]
let selectedBibIdx = null;            // bib box awaiting a face click, or null
```

### Canvas rendering

On load, and after every link change, redraw the canvas:

```js
function redraw() {
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const img = document.getElementById('photo');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const imgRect = getImageRect(img, canvas);

    // Draw bib boxes (orange; yellow if selected as link source)
    bibBoxes.forEach(function(b, i) {
        const r = LabelingCore.boxToCanvasRect(b, imgRect);
        ctx.strokeStyle = (i === selectedBibIdx) ? 'yellow' : 'rgba(255, 140, 0, 0.9)';
        ctx.lineWidth = (i === selectedBibIdx) ? 3 : 2;
        ctx.strokeRect(r.x, r.y, r.w, r.h);
    });

    // Draw face boxes (blue)
    faceBoxes.forEach(function(b) {
        const r = LabelingCore.boxToCanvasRect(b, imgRect);
        ctx.strokeStyle = 'rgba(60, 120, 255, 0.85)';
        ctx.lineWidth = 2;
        ctx.strokeRect(r.x, r.y, r.w, r.h);
    });

    // Draw link lines (grey, connecting box centres)
    ctx.strokeStyle = 'rgba(160, 160, 160, 0.7)';
    ctx.lineWidth = 1.5;
    links.forEach(function(lnk) {
        const bb = bibBoxes[lnk[0]];
        const fb = faceBoxes[lnk[1]];
        if (!bb || !fb) return;
        const bc = boxCenter(bb, imgRect);
        const fc = boxCenter(fb, imgRect);
        ctx.beginPath();
        ctx.moveTo(bc.x, bc.y);
        ctx.lineTo(fc.x, fc.y);
        ctx.stroke();
    });
}

function boxCenter(box, imgRect) {
    const tl = LabelingCore.normalToCanvas(box.x, box.y, imgRect);
    return {
        x: tl.x + box.w * imgRect.w / 2,
        y: tl.y + box.h * imgRect.h / 2,
    };
}
```

`getImageRect` follows the same pattern as in `bib_labeling_ui.js` — reads the
`<img>` element's bounding box relative to the canvas.

### Click handling

```js
canvas.addEventListener('click', function(e) {
    const imgRect = getImageRect(img, canvas);
    const pos = canvasPos(e, canvas);   // {x, y} in canvas pixels

    // Did the user click a bib box?
    const hitBib = bibBoxes.findIndex(function(b) {
        return LabelingCore.hitTestBox(pos.x, pos.y, b, imgRect);
    });
    if (hitBib >= 0) {
        selectedBibIdx = (selectedBibIdx === hitBib) ? null : hitBib;
        redraw();
        return;
    }

    // Did the user click a face box while a bib is selected?
    if (selectedBibIdx !== null) {
        const hitFace = faceBoxes.findIndex(function(b) {
            return LabelingCore.hitTestBox(pos.x, pos.y, b, imgRect);
        });
        if (hitFace >= 0) {
            links = toggleLink(links, selectedBibIdx, hitFace);
            selectedBibIdx = null;
            updateLinkCounter();
            redraw();
            saveLinksSoon();
            return;
        }
    }

    // Click missed everything — deselect
    selectedBibIdx = null;
    redraw();
});

function toggleLink(links, bibIdx, faceIdx) {
    const existing = links.findIndex(function(l) {
        return l[0] === bibIdx && l[1] === faceIdx;
    });
    if (existing >= 0) {
        return links.filter(function(_, i) { return i !== existing; });
    }
    return links.concat([[bibIdx, faceIdx]]);
}
```

### Saving

```js
let saveTimer = null;
function saveLinksSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveLinks, 500);
}

async function saveLinks() {
    const resp = await fetch('/api/bib_face_links/' + contentHash, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({links: links}),
    });
    if (!resp.ok) {
        const err = await resp.json();
        showStatus('Save failed: ' + (err.error || 'unknown'), true);
    }
}
```

### Link counter

```js
function updateLinkCounter() {
    const el = document.getElementById('linkCount');
    if (el) el.textContent = links.length + ' link' + (links.length === 1 ? '' : 's');
}
```

## Changes to `labeling.js` (`LabelingCore`)

Add `normalToCanvas` to the public exports if not already exported (check — it is
already exported). No other changes to `labeling.js` needed.

## Navigation links from existing pages

Optionally add a "Links" link from the bib and face labeling pages to `/links/<hash>`
for the current photo. This is a template-only change (one `<a>` tag in the nav area
of `labeling.html` and `face_labeling.html`) and can be done as part of this task or
deferred.

## Test strategy

- `test_link_photo_route()` — GET `/links/<hash>` returns 200 with expected template vars.
- `test_link_photo_unknown_hash()` — GET `/links/unknown` returns 404.
- Manual browser testing:
  1. Open `/links/<hash>`. Verify photo loads, bib boxes (orange) and face boxes (blue) drawn.
  2. Click a bib box — verify it turns yellow.
  3. Click a face box — verify a grey line appears and the link counter updates.
  4. Reload — verify links persist.
  5. Click the same bib then face again — verify line disappears (toggle).
  6. Click elsewhere — verify bib selection is cleared.

## Scope boundaries

- **In scope**: new route, template, JS file, `toggleLink` logic, save/load, navigation.
- **Out of scope**: a `/links/` listing page (can be added later), face labeling page
  changes, benchmark inspector display of links.
- **Do not** modify `LabelingUI`, the bib labeling page, or the face labeling page
  (except optionally adding a nav link).
- Box display is **read-only** — no drag, create, or delete on this page.
