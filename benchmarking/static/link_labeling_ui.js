/**
 * Link labeling UI — associate bib boxes with face boxes.
 *
 * Uses LabelingCore for coordinate utilities (boxToCanvasRect, hitTestBox,
 * normalToCanvas). No box editing — display is read-only.
 */

(function () {
    'use strict';

    // PAGE_DATA is populated from the #page-data JSON block and used by
    // shared helpers in labeling.js (navigate, etc.)
    window.PAGE_DATA = JSON.parse(document.getElementById('page-data').textContent);
    var contentHash = PAGE_DATA.content_hash;

    var bibBoxes = PAGE_DATA.bib_boxes;
    var faceBoxes = PAGE_DATA.face_boxes;
    var links = PAGE_DATA.links;       // [[bib_idx, face_idx], ...]
    var isProcessed = PAGE_DATA.is_processed;
    var selectedBibIdx = null;

    var canvas = document.getElementById('canvas');
    var ctx = canvas.getContext('2d');
    var img = document.getElementById('photo');

    // -------------------------------------------------------------------------
    // Image rect (object-fit: contain accounting)
    // -------------------------------------------------------------------------

    function getImageRect() {
        if (!img || !img.naturalWidth) return { x: 0, y: 0, w: canvas.width, h: canvas.height };
        var cw = canvas.width;
        var ch = canvas.height;
        var iw = img.naturalWidth;
        var ih = img.naturalHeight;
        var scale = Math.min(cw / iw, ch / ih);
        var rw = iw * scale;
        var rh = ih * scale;
        return { x: (cw - rw) / 2, y: (ch - rh) / 2, w: rw, h: rh };
    }

    // -------------------------------------------------------------------------
    // Canvas position from mouse event
    // -------------------------------------------------------------------------

    function canvasPos(e) {
        var rect = canvas.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    // -------------------------------------------------------------------------
    // Box centre in canvas pixels
    // -------------------------------------------------------------------------

    function boxCenter(box, imgRect) {
        var tl = LabelingCore.normalToCanvas(box.x, box.y, imgRect);
        return {
            x: tl.x + box.w * imgRect.w / 2,
            y: tl.y + box.h * imgRect.h / 2,
        };
    }

    // -------------------------------------------------------------------------
    // Rendering
    // -------------------------------------------------------------------------

    function redraw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        var imgRect = getImageRect();

        // Bib boxes — orange, yellow when selected
        bibBoxes.forEach(function (b, i) {
            var r = LabelingCore.boxToCanvasRect(b, imgRect);
            ctx.strokeStyle = (i === selectedBibIdx) ? 'yellow' : 'rgba(255, 140, 0, 0.9)';
            ctx.lineWidth = (i === selectedBibIdx) ? 3 : 2;
            ctx.strokeRect(r.x, r.y, r.w, r.h);

            // Bib number label
            var label = b.number || '';
            if (label) {
                ctx.font = '12px monospace';
                var metrics = ctx.measureText(label);
                var pad = 3;
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.fillRect(r.x, r.y - 16, metrics.width + pad * 2, 16);
                ctx.fillStyle = (i === selectedBibIdx) ? 'yellow' : 'rgba(255, 140, 0, 0.9)';
                ctx.fillText(label, r.x + pad, r.y - 4);
            }
        });

        // Face boxes — blue
        faceBoxes.forEach(function (b) {
            var r = LabelingCore.boxToCanvasRect(b, imgRect);
            ctx.strokeStyle = 'rgba(60, 120, 255, 0.85)';
            ctx.lineWidth = 2;
            ctx.strokeRect(r.x, r.y, r.w, r.h);

            var label = b.identity || '';
            if (label) {
                ctx.font = '12px monospace';
                var metrics = ctx.measureText(label);
                var pad = 3;
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.fillRect(r.x, r.y - 16, metrics.width + pad * 2, 16);
                ctx.fillStyle = 'rgba(60, 120, 255, 0.85)';
                ctx.fillText(label, r.x + pad, r.y - 4);
            }
        });

        // Link lines — grey, connecting box centres
        ctx.strokeStyle = 'rgba(160, 160, 160, 0.7)';
        ctx.lineWidth = 1.5;
        links.forEach(function (lnk) {
            var bb = bibBoxes[lnk[0]];
            var fb = faceBoxes[lnk[1]];
            if (!bb || !fb) return;
            var bc = boxCenter(bb, imgRect);
            var fc = boxCenter(fb, imgRect);
            ctx.beginPath();
            ctx.moveTo(bc.x, bc.y);
            ctx.lineTo(fc.x, fc.y);
            ctx.stroke();
        });
    }

    // -------------------------------------------------------------------------
    // Link toggling
    // -------------------------------------------------------------------------

    function toggleLink(bibIdx, faceIdx) {
        var existing = links.findIndex(function (l) {
            return l[0] === bibIdx && l[1] === faceIdx;
        });
        if (existing >= 0) {
            links = links.filter(function (_, i) { return i !== existing; });
        } else {
            links = links.concat([[bibIdx, faceIdx]]);
        }
    }

    // -------------------------------------------------------------------------
    // Link counter
    // -------------------------------------------------------------------------

    function updateLinkCounter() {
        var el = document.getElementById('linkCount');
        if (el) el.textContent = links.length + ' link' + (links.length === 1 ? '' : 's');
    }

    function updateProcessedUI() {
        var btn = document.getElementById('noLinksBtn');
        var stat = document.getElementById('processedStatus');
        if (btn) {
            btn.classList.toggle('processed', isProcessed);
            btn.textContent = isProcessed ? 'No Links ✓' : 'Mark as No Links';
        }
        if (stat) stat.textContent = isProcessed ? 'Yes' : '—';
    }

    function onNoLinksBtnClick() {
        clearTimeout(saveTimer);
        links = [];
        updateLinkCounter();
        redraw();
        fetch('/api/bib_face_links/' + contentHash, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ links: [] }),
        }).then(function (resp) {
            if (resp.ok) {
                isProcessed = true;
                updateProcessedUI();
                showStatus('Saved — no links', false);
            } else {
                resp.json().then(function (err) {
                    showStatus('Save failed: ' + (err.error || 'unknown'), true);
                });
            }
        }).catch(function (err) {
            showStatus('Save failed: ' + err.message, true);
        });
    }

    // -------------------------------------------------------------------------
    // Saving (debounced)
    // -------------------------------------------------------------------------

    var saveTimer = null;

    function saveLinksSoon() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveLinks, 500);
    }

    function saveLinks() {
        fetch('/api/bib_face_links/' + contentHash, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ links: links }),
        }).then(function (resp) {
            if (!resp.ok) {
                return resp.json().then(function (err) {
                    showStatus('Save failed: ' + (err.error || 'unknown'), true);
                });
            }
            isProcessed = true;
            updateProcessedUI();
        }).catch(function (err) {
            showStatus('Save failed: ' + err.message, true);
        });
    }

    // -------------------------------------------------------------------------
    // Click handling
    // -------------------------------------------------------------------------

    canvas.addEventListener('click', function (e) {
        var imgRect = getImageRect();
        var pos = canvasPos(e);

        // Did the user click a bib box?
        var hitBib = bibBoxes.findIndex(function (b) {
            return LabelingCore.hitTestBox(pos.x, pos.y, b, imgRect);
        });
        if (hitBib >= 0) {
            selectedBibIdx = (selectedBibIdx === hitBib) ? null : hitBib;
            redraw();
            return;
        }

        // Did the user click a face box while a bib is selected?
        if (selectedBibIdx !== null) {
            var hitFace = faceBoxes.findIndex(function (b) {
                return LabelingCore.hitTestBox(pos.x, pos.y, b, imgRect);
            });
            if (hitFace >= 0) {
                toggleLink(selectedBibIdx, hitFace);
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

    // -------------------------------------------------------------------------
    // Canvas sizing (ResizeObserver)
    // -------------------------------------------------------------------------

    function resizeCanvas() {
        var container = canvas.parentElement;
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
        redraw();
    }

    var ro = new ResizeObserver(function () { resizeCanvas(); });
    ro.observe(canvas.parentElement);

    // -------------------------------------------------------------------------
    // Keyboard shortcuts
    // -------------------------------------------------------------------------

    document.addEventListener('keydown', function (e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

        if (e.key === 'ArrowLeft') { navigate('prev'); }
        else if (e.key === 'ArrowRight') { navigate('next'); }
        else if (e.key === 'n') {
            e.preventDefault();
            onNoLinksBtnClick();
        }
    });

    // -------------------------------------------------------------------------
    // Button wiring
    // -------------------------------------------------------------------------

    var noLinksBtn = document.getElementById('noLinksBtn');
    if (noLinksBtn) noLinksBtn.addEventListener('click', onNoLinksBtnClick);

    // -------------------------------------------------------------------------
    // Initial draw (after image loads)
    // -------------------------------------------------------------------------

    if (img.complete && img.naturalWidth) {
        resizeCanvas();
    } else {
        img.addEventListener('load', resizeCanvas);
    }

})();
