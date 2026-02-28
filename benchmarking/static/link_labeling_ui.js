/**
 * Link labeling UI — associate bib boxes with face boxes.
 *
 * Uses PhotoCanvas for scope-aware rendering (drawBox, drawLinkLine).
 * Uses LabelingCore for click hit-testing (hitTestBox). No box editing — display is read-only.
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
    var img = document.getElementById('photo');
    var _canvas = PhotoCanvas.create({ imgEl: img, canvasEl: canvas });

    // -------------------------------------------------------------------------
    // Canvas position from mouse event (local — used for click hit-testing)
    // -------------------------------------------------------------------------

    function canvasPos(e) {
        var rect = canvas.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    // -------------------------------------------------------------------------
    // Rendering
    // -------------------------------------------------------------------------

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
        if (el) {
            el.textContent = links.length + ' link' + (links.length === 1 ? '' : 's');
            el.classList.toggle('warning', links.length < PAGE_DATA.numbered_bib_count);
        }
    }

    function updateProcessedUI() {
        var btn = document.getElementById('noLinksBtn');
        var stat = document.getElementById('processedStatus');
        var hasLinks = links.length > 0;
        if (btn) {
            btn.classList.toggle('processed', isProcessed && !hasPendingChanges);
            if (hasPendingChanges) {
                btn.textContent = hasLinks ? 'Save Links\u2026' : 'Save\u2026';
            } else if (isProcessed) {
                btn.textContent = hasLinks ? 'Links Saved \u2713' : 'No Links \u2713';
            } else {
                btn.textContent = hasLinks ? 'Save Links' : 'Mark as No Links';
            }
        }
        if (stat) stat.textContent = isProcessed ? 'Yes' : '—';
    }

    function onSaveDoneBtn() {
        clearTimeout(saveTimer);
        hasPendingChanges = false;
        var hasLinks = links.length > 0;
        fetch('/api/associations/' + contentHash, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ links: links }),
        }).then(function (resp) {
            if (resp.ok) {
                isProcessed = true;
                updateProcessedUI();
                showStatus(hasLinks ? 'Links saved' : 'Saved \u2014 no links', false);
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
    // Saving (debounced, with promise tracking for safe navigation)
    // -------------------------------------------------------------------------

    var saveTimer = null;
    var savePromise = null;
    var hasPendingChanges = false;

    function saveLinksSoon() {
        clearTimeout(saveTimer);
        hasPendingChanges = true;
        updateProcessedUI();  // update button label while unsaved
        saveTimer = setTimeout(function () { saveLinks(); }, 500);
    }

    function saveLinks() {
        clearTimeout(saveTimer);
        saveTimer = null;
        hasPendingChanges = false;
        savePromise = fetch('/api/associations/' + contentHash, {
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
        return savePromise;
    }

    // Navigate to url, flushing any pending save first.
    function navigate(url) {
        if (!url) return;
        if (hasPendingChanges) {
            clearTimeout(saveTimer);
            hasPendingChanges = false;
            showStatus('Saving\u2026', false);
            saveLinks().then(function () { window.location.href = url; });
        } else if (savePromise) {
            savePromise.then(function () { window.location.href = url; });
        } else {
            window.location.href = url;
        }
    }

    window.navigate = navigate;

    // -------------------------------------------------------------------------
    // Click handling
    // -------------------------------------------------------------------------

    canvas.addEventListener('click', function (e) {
        var imgRect = _canvas.getImageRect();
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

    _canvas.startResizeObserver(redraw);

    // -------------------------------------------------------------------------
    // Keyboard shortcuts
    // -------------------------------------------------------------------------

    document.addEventListener('keydown', function (e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

        if (e.key === 'ArrowLeft') { navigate(PAGE_DATA.prevUrl); }
        else if (e.key === 'ArrowRight') { navigate(PAGE_DATA.nextUrl); }
        else if (e.key === 'n' || e.key === 'Enter') {
            e.preventDefault();
            onSaveDoneBtn();
        }
    });

    // -------------------------------------------------------------------------
    // Button wiring
    // -------------------------------------------------------------------------

    var noLinksBtn = document.getElementById('noLinksBtn');
    if (noLinksBtn) noLinksBtn.addEventListener('click', onSaveDoneBtn);

    // -------------------------------------------------------------------------
    // Initial draw (after image loads)
    // -------------------------------------------------------------------------

    updateProcessedUI();

    if (img.complete && img.naturalWidth) {
        _canvas.resizeCanvas();
        redraw();
    } else {
        img.addEventListener('load', function () { _canvas.resizeCanvas(); redraw(); });
    }

})();
