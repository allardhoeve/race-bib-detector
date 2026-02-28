/**
 * Canvas-based labeling UI for bib and face bounding box annotation.
 *
 * Three namespaces:
 *   LabelingCore — pure logic (coordinate math, hit testing, box ops). Testable in Node.
 *   PhotoCanvas  — shared canvas rendering (drawBox, drawLinkLine, resizeCanvas). Browser only.
 *   LabelingUI   — DOM/canvas interaction, wraps PhotoCanvas. Browser only.
 */

// =============================================================================
// LabelingCore — pure logic, no DOM
// =============================================================================

var LabelingCore = (function () {
    'use strict';

    var HANDLE_RADIUS = 6;
    var MIN_BOX_PX = 10;

    // --- Coordinate conversion ---

    function normalToCanvas(nx, ny, imgRect) {
        return {
            x: imgRect.x + nx * imgRect.w,
            y: imgRect.y + ny * imgRect.h,
        };
    }

    function canvasToNormal(cx, cy, imgRect) {
        return {
            x: (cx - imgRect.x) / imgRect.w,
            y: (cy - imgRect.y) / imgRect.h,
        };
    }

    function boxToCanvasRect(box, imgRect) {
        var tl = normalToCanvas(box.x, box.y, imgRect);
        return {
            x: tl.x,
            y: tl.y,
            w: box.w * imgRect.w,
            h: box.h * imgRect.h,
        };
    }

    // --- Hit testing ---

    function hitTestBox(cx, cy, box, imgRect) {
        var r = boxToCanvasRect(box, imgRect);
        return cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h;
    }

    /**
     * Returns handle index 0-7 (corners then midpoints) or -1.
     * Order: TL, TR, BR, BL, T, R, B, L
     */
    function hitTestHandle(cx, cy, box, imgRect) {
        var r = boxToCanvasRect(box, imgRect);
        var handles = getHandlePositions(r);
        for (var i = 0; i < handles.length; i++) {
            var dx = cx - handles[i].x;
            var dy = cy - handles[i].y;
            if (dx * dx + dy * dy <= HANDLE_RADIUS * HANDLE_RADIUS) {
                return i;
            }
        }
        return -1;
    }

    function getHandlePositions(rect) {
        var mx = rect.x + rect.w / 2;
        var my = rect.y + rect.h / 2;
        return [
            { x: rect.x, y: rect.y },                  // 0 TL
            { x: rect.x + rect.w, y: rect.y },          // 1 TR
            { x: rect.x + rect.w, y: rect.y + rect.h }, // 2 BR
            { x: rect.x, y: rect.y + rect.h },          // 3 BL
            { x: mx, y: rect.y },                        // 4 T
            { x: rect.x + rect.w, y: my },               // 5 R
            { x: mx, y: rect.y + rect.h },               // 6 B
            { x: rect.x, y: my },                         // 7 L
        ];
    }

    // --- Box model operations ---

    function clampNormal(v) {
        return Math.max(0, Math.min(1, v));
    }

    function createBox(x, y, w, h, extra) {
        var box = { x: x, y: y, w: w, h: h };
        if (extra) {
            for (var k in extra) {
                if (extra.hasOwnProperty(k)) box[k] = extra[k];
            }
        }
        return box;
    }

    function meetsMinSize(box, imgRect) {
        return (box.w * imgRect.w >= MIN_BOX_PX) && (box.h * imgRect.h >= MIN_BOX_PX);
    }

    /**
     * Compute IoU between two normalised boxes.
     */
    function computeIoU(a, b) {
        var x1 = Math.max(a.x, b.x);
        var y1 = Math.max(a.y, b.y);
        var x2 = Math.min(a.x + a.w, b.x + b.w);
        var y2 = Math.min(a.y + a.h, b.y + b.h);
        var inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
        if (inter === 0) return 0;
        var areaA = a.w * a.h;
        var areaB = b.w * b.h;
        return inter / (areaA + areaB - inter);
    }

    /**
     * Check if a suggestion overlaps any existing box (IoU > threshold).
     */
    function suggestionOverlaps(suggestion, boxes, threshold) {
        if (typeof threshold === 'undefined') threshold = 0.3;
        for (var i = 0; i < boxes.length; i++) {
            if (computeIoU(suggestion, boxes[i]) > threshold) return true;
        }
        return false;
    }

    /**
     * Apply a handle drag. Returns new {x, y, w, h} in normal coords.
     */
    function applyHandleDrag(box, handleIdx, nx, ny) {
        var x1 = box.x, y1 = box.y;
        var x2 = box.x + box.w, y2 = box.y + box.h;
        nx = clampNormal(nx);
        ny = clampNormal(ny);

        switch (handleIdx) {
            case 0: x1 = nx; y1 = ny; break;       // TL
            case 1: x2 = nx; y1 = ny; break;       // TR
            case 2: x2 = nx; y2 = ny; break;       // BR
            case 3: x1 = nx; y2 = ny; break;       // BL
            case 4: y1 = ny; break;                 // T
            case 5: x2 = nx; break;                 // R
            case 6: y2 = ny; break;                 // B
            case 7: x1 = nx; break;                 // L
        }

        // Ensure positive dimensions (swap if dragged past opposite edge)
        if (x1 > x2) { var tx = x1; x1 = x2; x2 = tx; }
        if (y1 > y2) { var ty = y1; y1 = y2; y2 = ty; }

        return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
    }

    /**
     * Move a box by delta in normal coords, clamped to [0,1].
     */
    function moveBox(box, dnx, dny) {
        var nx = clampNormal(box.x + dnx);
        var ny = clampNormal(box.y + dny);
        // Clamp so box stays within image
        if (nx + box.w > 1) nx = 1 - box.w;
        if (ny + box.h > 1) ny = 1 - box.h;
        if (nx < 0) nx = 0;
        if (ny < 0) ny = 0;
        return { x: nx, y: ny, w: box.w, h: box.h };
    }

    var BOX_COLORS = {
        bib: '#00ff88',
        not_bib: '#ff4444',
        bib_obscured: '#ffaa00',
        bib_clipped: '#88ccff',
        keep: '#00aaff',
        exclude: '#ff4444',
        uncertain: '#888888',
    };

    return {
        HANDLE_RADIUS: HANDLE_RADIUS,
        MIN_BOX_PX: MIN_BOX_PX,
        BOX_COLORS: BOX_COLORS,
        normalToCanvas: normalToCanvas,
        canvasToNormal: canvasToNormal,
        boxToCanvasRect: boxToCanvasRect,
        hitTestBox: hitTestBox,
        hitTestHandle: hitTestHandle,
        getHandlePositions: getHandlePositions,
        clampNormal: clampNormal,
        createBox: createBox,
        meetsMinSize: meetsMinSize,
        computeIoU: computeIoU,
        suggestionOverlaps: suggestionOverlaps,
        applyHandleDrag: applyHandleDrag,
        moveBox: moveBox,
    };
})();


// =============================================================================
// PhotoCanvas — shared canvas rendering (browser only)
// =============================================================================

var PhotoCanvas = (function () {
    'use strict';
    var C = LabelingCore;

    function create(opts) {
        var imgEl = opts.imgEl;
        var canvasEl = opts.canvasEl;
        var ctx = canvasEl.getContext('2d');

        function getImageRect() {
            if (!imgEl || !imgEl.naturalWidth) return { x: 0, y: 0, w: canvasEl.width, h: canvasEl.height };
            var cw = canvasEl.width;
            var ch = canvasEl.height;
            var iw = imgEl.naturalWidth;
            var ih = imgEl.naturalHeight;
            var scale = Math.min(cw / iw, ch / ih);
            var rw = iw * scale;
            var rh = ih * scale;
            return { x: (cw - rw) / 2, y: (ch - rh) / 2, w: rw, h: rh };
        }

        function clear() {
            ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        }

        function drawBox(box, mode, isSelected) {
            var imgRect = getImageRect();
            var r = C.boxToCanvasRect(box, imgRect);
            var colorKey = box.scope || (mode === 'bib' ? 'bib' : 'keep');
            var color = C.BOX_COLORS[colorKey] || '#00ff88';

            ctx.strokeStyle = color;
            ctx.lineWidth = isSelected ? 3 : 2;
            ctx.setLineDash([]);
            ctx.strokeRect(r.x, r.y, r.w, r.h);

            var label = mode === 'bib' ? (box.number || '') : (box.identity || box.scope || '');
            if (mode === 'face' && box.tags && box.tags.length) {
                label += ' [' + box.tags.join(',') + ']';
            }
            if (label) {
                ctx.font = '12px monospace';
                var metrics = ctx.measureText(label);
                var pad = 3;
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.fillRect(r.x, r.y - 16, metrics.width + pad * 2, 16);
                ctx.fillStyle = color;
                ctx.fillText(label, r.x + pad, r.y - 4);
            }

            if (isSelected) {
                var handles = C.getHandlePositions(r);
                ctx.fillStyle = color;
                for (var i = 0; i < handles.length; i++) {
                    ctx.beginPath();
                    ctx.arc(handles[i].x, handles[i].y, C.HANDLE_RADIUS, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
        }

        function drawLinkLine(bibBox, faceBox) {
            var imgRect = getImageRect();
            var btl = C.normalToCanvas(bibBox.x, bibBox.y, imgRect);
            var ftl = C.normalToCanvas(faceBox.x, faceBox.y, imgRect);
            var bc = { x: btl.x + bibBox.w * imgRect.w / 2, y: btl.y + bibBox.h * imgRect.h / 2 };
            var fc = { x: ftl.x + faceBox.w * imgRect.w / 2, y: ftl.y + faceBox.h * imgRect.h / 2 };
            ctx.strokeStyle = 'rgba(160, 160, 160, 0.7)';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(bc.x, bc.y);
            ctx.lineTo(fc.x, fc.y);
            ctx.stroke();
        }

        function resizeCanvas() {
            canvasEl.width = canvasEl.parentElement.clientWidth;
            canvasEl.height = canvasEl.parentElement.clientHeight;
        }

        function startResizeObserver(onResize) {
            var ro = new ResizeObserver(function () {
                resizeCanvas();
                onResize();
            });
            ro.observe(canvasEl.parentElement);
        }

        return { getImageRect: getImageRect, clear: clear, drawBox: drawBox, drawLinkLine: drawLinkLine, resizeCanvas: resizeCanvas, startResizeObserver: startResizeObserver, ctx: ctx };
    }

    return { create: create };
})();


// =============================================================================
// LabelingUI — DOM/canvas interaction (browser only)
// =============================================================================

var LabelingUI = (function () {
    'use strict';

    var C = LabelingCore;
    var _canvas;

    var state = {
        mode: 'bib',           // 'bib' or 'face'
        boxes: [],
        suggestions: [],
        selectedIdx: -1,
        interaction: 'idle',   // idle | drawing | resizing | moving
        // Drawing state
        drawStart: null,       // {nx, ny} normal coords
        drawCurrent: null,
        // Resize state
        resizeHandleIdx: -1,
        // Move state
        moveStart: null,       // {nx, ny}
        moveOrigBox: null,
        // Config
        contentHash: '',
        apiBase: '',
        imgEl: null,
        canvasEl: null,
        ctx: null,
        // Callbacks
        onBoxesChanged: null,
        onBoxSelected: null,
    };

    // --- Rendering ---

    function render() {
        if (!_canvas) return;
        var ctx = _canvas.ctx;
        _canvas.clear();
        var imgRect = _canvas.getImageRect();

        // Draw suggestions (dashed, unmatched only)
        for (var i = 0; i < state.suggestions.length; i++) {
            var sugg = state.suggestions[i];
            if (C.suggestionOverlaps(sugg, state.boxes)) continue;
            drawSuggestion(ctx, sugg, imgRect, i);
        }

        // Draw user boxes
        for (var j = 0; j < state.boxes.length; j++) {
            var isSelected = (j === state.selectedIdx);
            _canvas.drawBox(state.boxes[j], state.mode, isSelected);
        }

        // Draw in-progress drawing
        if (state.interaction === 'drawing' && state.drawStart && state.drawCurrent) {
            var s = state.drawStart;
            var c = state.drawCurrent;
            var x = Math.min(s.nx, c.nx);
            var y = Math.min(s.ny, c.ny);
            var w = Math.abs(c.nx - s.nx);
            var h = Math.abs(c.ny - s.ny);
            var tl = C.normalToCanvas(x, y, imgRect);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(tl.x, tl.y, w * imgRect.w, h * imgRect.h);
            ctx.setLineDash([]);
        }
    }

    function drawSuggestion(ctx, sugg, imgRect, idx) {
        var r = C.boxToCanvasRect(sugg, imgRect);
        ctx.strokeStyle = 'rgba(255, 255, 100, 0.6)';
        ctx.lineWidth = 2;
        ctx.setLineDash([8, 4]);
        ctx.strokeRect(r.x, r.y, r.w, r.h);
        ctx.setLineDash([]);

        // Label
        var label = sugg.number || ('face ' + (idx + 1));
        ctx.font = '11px monospace';
        var metrics = ctx.measureText(label);
        var pad = 3;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(r.x, r.y - 14, metrics.width + pad * 2, 14);
        ctx.fillStyle = 'rgba(255, 255, 100, 0.8)';
        ctx.fillText(label, r.x + pad, r.y - 3);
    }

    // --- Mouse interaction ---

    function getCanvasPos(e) {
        var rect = state.canvasEl.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    function onMouseDown(e) {
        if (e.button !== 0) return;
        var pos = getCanvasPos(e);
        var imgRect = _canvas.getImageRect();

        // Check if clicking a handle on selected box
        if (state.selectedIdx >= 0) {
            var hi = C.hitTestHandle(pos.x, pos.y, state.boxes[state.selectedIdx], imgRect);
            if (hi >= 0) {
                state.interaction = 'resizing';
                state.resizeHandleIdx = hi;
                e.preventDefault();
                return;
            }
        }

        // Check if clicking inside an existing box
        for (var i = state.boxes.length - 1; i >= 0; i--) {
            if (C.hitTestBox(pos.x, pos.y, state.boxes[i], imgRect)) {
                selectBox(i);
                state.interaction = 'moving';
                var n = C.canvasToNormal(pos.x, pos.y, imgRect);
                state.moveStart = n;
                state.moveOrigBox = { x: state.boxes[i].x, y: state.boxes[i].y, w: state.boxes[i].w, h: state.boxes[i].h };
                e.preventDefault();
                return;
            }
        }

        // Check if clicking a suggestion
        for (var s = state.suggestions.length - 1; s >= 0; s--) {
            var sugg = state.suggestions[s];
            if (C.suggestionOverlaps(sugg, state.boxes)) continue;
            if (C.hitTestBox(pos.x, pos.y, sugg, imgRect)) {
                acceptSuggestion(s);
                e.preventDefault();
                return;
            }
        }

        // Start drawing new box (only if inside image area)
        var n2 = C.canvasToNormal(pos.x, pos.y, imgRect);
        if (n2.x >= 0 && n2.x <= 1 && n2.y >= 0 && n2.y <= 1) {
            state.interaction = 'drawing';
            state.drawStart = { nx: n2.x, ny: n2.y };
            state.drawCurrent = { nx: n2.x, ny: n2.y };
            selectBox(-1);
            e.preventDefault();
        }
    }

    function onMouseMove(e) {
        var pos = getCanvasPos(e);
        var imgRect = _canvas.getImageRect();
        var n = C.canvasToNormal(pos.x, pos.y, imgRect);

        if (state.interaction === 'drawing') {
            state.drawCurrent = { nx: C.clampNormal(n.x), ny: C.clampNormal(n.y) };
            render();
        } else if (state.interaction === 'resizing' && state.selectedIdx >= 0) {
            var newCoords = C.applyHandleDrag(
                state.boxes[state.selectedIdx],
                state.resizeHandleIdx,
                n.x, n.y
            );
            state.boxes[state.selectedIdx].x = newCoords.x;
            state.boxes[state.selectedIdx].y = newCoords.y;
            state.boxes[state.selectedIdx].w = newCoords.w;
            state.boxes[state.selectedIdx].h = newCoords.h;
            render();
        } else if (state.interaction === 'moving' && state.selectedIdx >= 0) {
            var dnx = n.x - state.moveStart.x;
            var dny = n.y - state.moveStart.y;
            var moved = C.moveBox(state.moveOrigBox, dnx, dny);
            state.boxes[state.selectedIdx].x = moved.x;
            state.boxes[state.selectedIdx].y = moved.y;
            render();
        } else {
            // Update cursor
            updateCursor(pos, imgRect);
        }
    }

    function onMouseUp(e) {
        var imgRect = _canvas.getImageRect();

        if (state.interaction === 'drawing' && state.drawStart && state.drawCurrent) {
            var s = state.drawStart;
            var c = state.drawCurrent;
            var x = Math.min(s.nx, c.nx);
            var y = Math.min(s.ny, c.ny);
            var w = Math.abs(c.nx - s.nx);
            var h = Math.abs(c.ny - s.ny);
            var newBox = { x: x, y: y, w: w, h: h };

            if (C.meetsMinSize(newBox, imgRect)) {
                if (state.mode === 'bib') {
                    newBox.number = '';
                    newBox.scope = 'bib';
                } else {
                    newBox.scope = 'keep';
                    newBox.identity = '';
                    newBox.tags = [];
                }
                state.boxes.push(newBox);
                selectBox(state.boxes.length - 1);
                notifyBoxesChanged();
            }
        }

        state.interaction = 'idle';
        state.drawStart = null;
        state.drawCurrent = null;
        state.resizeHandleIdx = -1;
        state.moveStart = null;
        state.moveOrigBox = null;
        render();
    }

    function updateCursor(pos, imgRect) {
        var canvas = state.canvasEl;

        // Check handles first
        if (state.selectedIdx >= 0) {
            var hi = C.hitTestHandle(pos.x, pos.y, state.boxes[state.selectedIdx], imgRect);
            if (hi >= 0) {
                var cursors = ['nwse-resize', 'nesw-resize', 'nwse-resize', 'nesw-resize',
                               'ns-resize', 'ew-resize', 'ns-resize', 'ew-resize'];
                canvas.style.cursor = cursors[hi];
                return;
            }
        }

        // Check boxes
        for (var i = state.boxes.length - 1; i >= 0; i--) {
            if (C.hitTestBox(pos.x, pos.y, state.boxes[i], imgRect)) {
                canvas.style.cursor = 'move';
                return;
            }
        }

        // Check suggestions
        for (var s = 0; s < state.suggestions.length; s++) {
            if (C.suggestionOverlaps(state.suggestions[s], state.boxes)) continue;
            if (C.hitTestBox(pos.x, pos.y, state.suggestions[s], imgRect)) {
                canvas.style.cursor = 'pointer';
                return;
            }
        }

        canvas.style.cursor = 'crosshair';
    }

    // --- Box operations ---

    function selectBox(idx) {
        state.selectedIdx = idx;
        render();
        if (state.onBoxSelected) {
            state.onBoxSelected(idx, idx >= 0 ? state.boxes[idx] : null);
        }
    }

    function deleteSelected() {
        if (state.selectedIdx >= 0 && state.selectedIdx < state.boxes.length) {
            state.boxes.splice(state.selectedIdx, 1);
            state.selectedIdx = -1;
            render();
            notifyBoxesChanged();
        }
    }

    function acceptSuggestion(idx) {
        var sugg = state.suggestions[idx];
        var newBox = { x: sugg.x, y: sugg.y, w: sugg.w, h: sugg.h };
        if (state.mode === 'bib') {
            newBox.number = sugg.number || '';
            newBox.scope = 'bib';
        } else {
            newBox.scope = 'keep';
            newBox.identity = '';
            newBox.tags = [];
        }
        state.boxes.push(newBox);
        selectBox(state.boxes.length - 1);
        notifyBoxesChanged();
    }

    function cycleNextSuggestion() {
        for (var i = 0; i < state.suggestions.length; i++) {
            var sugg = state.suggestions[i];
            if (!C.suggestionOverlaps(sugg, state.boxes)) {
                // Scroll suggestion into view and flash it
                acceptSuggestion(i);
                return;
            }
        }
    }

    function notifyBoxesChanged() {
        if (state.onBoxesChanged) {
            state.onBoxesChanged(state.boxes);
        }
    }

    // --- Canvas sizing ---

    function resizeCanvas() {
        _canvas.resizeCanvas();
        render();
    }

    // --- API integration ---

    function fetchBoxes() {
        var endpoint = state.mode === 'bib'
            ? state.apiBase + '/api/bibs/' + state.contentHash
            : state.apiBase + '/api/faces/' + state.contentHash;

        return fetch(endpoint)
            .then(function (resp) {
                if (!resp.ok) throw new Error('Failed to load boxes');
                return resp.json();
            })
            .then(function (data) {
                state.boxes = data.boxes || [];
                state.suggestions = data.suggestions || [];
                state.selectedIdx = -1;
                render();
                notifyBoxesChanged();
                return data;
            });
    }

    // --- Keyboard ---

    function onKeyDown(e) {
        // Don't handle keys when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        if (e.key === 'Delete' || e.key === 'Backspace') {
            e.preventDefault();
            deleteSelected();
        } else if (e.key === 'Tab') {
            e.preventDefault();
            cycleNextSuggestion();
        } else if (e.key === 'Escape') {
            selectBox(-1);
        }
    }

    // --- Init ---

    function init(opts) {
        state.mode = opts.mode || 'bib';
        state.contentHash = opts.contentHash || '';
        state.apiBase = opts.apiBase || '';
        state.onBoxesChanged = opts.onBoxesChanged || null;
        state.onBoxSelected = opts.onBoxSelected || null;

        state.imgEl = opts.imgEl;
        state.canvasEl = opts.canvasEl;
        state.ctx = state.canvasEl.getContext('2d');

        _canvas = PhotoCanvas.create({ imgEl: state.imgEl, canvasEl: state.canvasEl });

        // Event listeners
        state.canvasEl.addEventListener('mousedown', onMouseDown);
        state.canvasEl.addEventListener('mousemove', onMouseMove);
        state.canvasEl.addEventListener('mouseup', onMouseUp);
        document.addEventListener('keydown', onKeyDown);

        // Resize observer
        _canvas.startResizeObserver(function () { render(); });

        // Initial resize
        resizeCanvas();

        // Load boxes
        if (state.contentHash) {
            fetchBoxes();
        }
    }

    return {
        init: init,
        getState: function () { return state; },
        selectBox: selectBox,
        deleteSelected: deleteSelected,
        render: render,
        fetchBoxes: fetchBoxes,
        resizeCanvas: resizeCanvas,
    };
})();


// Node.js export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LabelingCore: LabelingCore };
}

// =============================================================================
// Shared page helpers (used by bib_labeling_ui.js and face_labeling_ui.js)
// =============================================================================

function setSplit(split) {
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

function navigate(url) {
    if (url) window.location.href = url;
}

function navigateUnlabeled() {
    const url = PAGE_DATA.nextUnlabeledUrl;
    if (url) window.location.href = url;
}

function applyFilter() {
    const newFilter = document.getElementById('filter').value;
    window.location.href = PAGE_DATA.labelsIndexUrl + '?filter=' + newFilter;
}
