let currentSplit = PAGE_DATA.split;
const contentHash = PAGE_DATA.contentHash;

function getSelectedFaceTags() {
    return Array.from(document.querySelectorAll('input[name="face_tags"]:checked'))
                .map(cb => cb.value);
}

function onSplitClick(split) {
    currentSplit = split;
    setSplit(split);
}

// --- Identity autocomplete ---
function loadIdentities() {
    fetch('/api/identities')
        .then(r => r.json())
        .then(data => {
            const dl = document.getElementById('identityList');
            dl.innerHTML = '';
            (data.identities || []).forEach(id => {
                const opt = document.createElement('option');
                opt.value = id;
                dl.appendChild(opt);
            });
        });
}

// --- Assign anonymous identity ---
async function assignAnonymous() {
    const state = LabelingUI.getState();
    if (state.selectedIdx < 0) return;
    const resp = await fetch('/api/identities');
    const data = await resp.json();
    const existing = (data.identities || [])
        .filter(id => /^anon-\d+$/.test(id))
        .map(id => parseInt(id.split('-')[1], 10));
    const next = existing.length ? Math.max(...existing) + 1 : 1;
    const name = 'anon-' + next;
    document.getElementById('faceIdentity').value = name;
    state.boxes[state.selectedIdx].identity = name;
    await fetch('/api/identities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    });
    renderBoxList(state.boxes);
    LabelingUI.render();
    loadIdentities();
}

// --- Identity suggestions ---
let _suggestAbort = null;
function fetchIdentitySuggestions(box, confirmIdentity) {
    const container = document.getElementById('identitySuggestions');
    container.innerHTML = '';
    if (!box || !box.w || !box.h) return;
    if (_suggestAbort) _suggestAbort.abort();
    _suggestAbort = new AbortController();
    const params = new URLSearchParams({
        box_x: box.x, box_y: box.y, box_w: box.w, box_h: box.h, k: 5
    });
    fetch('/api/faces/' + contentHash + '/suggestions?' + params, {signal: _suggestAbort.signal})
        .then(r => r.json())
        .then(data => {
            container.innerHTML = '';
            if (confirmIdentity) {
                const match = (data.suggestions || []).find(s => s.identity === confirmIdentity);
                if (match?.samples?.length > 0) {
                    const label = document.createElement('span');
                    label.className = 'confirm-label';
                    label.textContent = 'other ' + confirmIdentity + ':';
                    container.appendChild(label);
                    match.samples.forEach(({content_hash, box_index}) => {
                        const img = document.createElement('img');
                        img.src = '/api/faces/' + content_hash + '/crop/' + box_index;
                        img.className = 'confirm-crop';
                        container.appendChild(img);
                    });
                }
            } else {
                (data.suggestions || []).forEach(s => {
                    const chip = document.createElement('span');
                    chip.className = 'suggestion-chip';
                    chip.textContent = s.identity + ' ' + Math.round(s.similarity * 100) + '%';
                    if (s.samples?.length > 0) {
                        const tooltip = document.createElement('span');
                        tooltip.className = 'crop-tooltip';
                        s.samples.forEach(({content_hash, box_index}) => {
                            const img = document.createElement('img');
                            img.src = '/api/faces/' + content_hash + '/crop/' + box_index;
                            tooltip.appendChild(img);
                        });
                        chip.appendChild(tooltip);
                    }
                    chip.addEventListener('click', () => {
                        document.getElementById('faceIdentity').value = s.identity;
                        const state = LabelingUI.getState();
                        if (state.selectedIdx >= 0) {
                            state.boxes[state.selectedIdx].identity = s.identity;
                            renderBoxList(state.boxes);
                            LabelingUI.render();
                        }
                    });
                    container.appendChild(chip);
                });
            }
        })
        .catch(e => { if (e.name !== 'AbortError') console.warn('Suggestion fetch failed:', e); });
}

// --- Box list rendering ---
function renderBoxList(boxes) {
    const list = document.getElementById('boxList');
    list.innerHTML = '';
    boxes.forEach((box, i) => {
        const li = document.createElement('li');
        li.className = 'box-item' + (i === LabelingUI.getState().selectedIdx ? ' selected' : '');
        let label = (box.identity || box.scope || 'keep');
        const boxTags = box.tags || [];
        if (boxTags.length) label += ' [' + boxTags.join(',') + ']';
        li.innerHTML = '<span class="box-label">' + label + '</span>' +
            '<span class="box-delete" data-idx="' + i + '">×</span>';
        li.addEventListener('click', function(e) {
            if (e.target.classList.contains('box-delete')) {
                LabelingUI.getState().selectedIdx = parseInt(e.target.dataset.idx);
                LabelingUI.deleteSelected();
            } else {
                LabelingUI.selectBox(i);
            }
        });
        list.appendChild(li);
    });

    // Update face count display
    const keepCount = boxes.filter(b => (b.scope || 'keep') === 'keep').length;
    document.getElementById('faceCountDisplay').textContent = 'Keep faces: ' + keepCount;
}

function onBoxSelected(idx, box) {
    const editor = document.getElementById('boxEditor');
    if (idx < 0 || !box) {
        editor.classList.remove('visible');
        return;
    }
    editor.classList.add('visible');
    const radios = document.querySelectorAll('input[name="faceScope"]');
    radios.forEach(r => { r.checked = r.value === (box.scope || 'keep'); });
    document.getElementById('faceIdentity').value = box.identity || '';

    // Set box tag checkboxes
    const boxTags = box.tags || [];
    document.querySelectorAll('input[name="box_tags"]').forEach(cb => {
        cb.checked = boxTags.includes(cb.value);
    });

    document.querySelectorAll('.box-item').forEach((el, i) => {
        el.classList.toggle('selected', i === idx);
    });

    document.getElementById('faceIdentity').focus();

    // Fetch suggestions: chips if unlabeled, confirmation crops if already identified
    fetchIdentitySuggestions(box, box.identity || null);
}

// Update box when editor changes
document.getElementById('faceIdentity').addEventListener('input', function() {
    const state = LabelingUI.getState();
    if (state.selectedIdx >= 0) {
        state.boxes[state.selectedIdx].identity = this.value;
        renderBoxList(state.boxes);
        LabelingUI.render();
    }
});

document.querySelectorAll('input[name="faceScope"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const state = LabelingUI.getState();
        if (state.selectedIdx >= 0) {
            state.boxes[state.selectedIdx].scope = this.value;
            renderBoxList(state.boxes);
            LabelingUI.render();
        }
    });
});

document.querySelectorAll('input[name="box_tags"]').forEach(cb => {
    cb.addEventListener('change', function() {
        const state = LabelingUI.getState();
        if (state.selectedIdx >= 0) {
            const tags = Array.from(document.querySelectorAll('input[name="box_tags"]:checked'))
                .map(c => c.value);
            state.boxes[state.selectedIdx].tags = tags;
            renderBoxList(state.boxes);
            LabelingUI.render();
        }
    });
});

// --- Save ---
async function save() {
    const state = LabelingUI.getState();

    // Auto-add new identities
    const newIdentities = state.boxes
        .filter(b => b.identity && b.identity.trim())
        .map(b => b.identity.trim());
    for (const name of new Set(newIdentities)) {
        await fetch('/api/identities', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
    }

    const data = {
        boxes: state.boxes.map(b => ({
            x: b.x, y: b.y, w: b.w, h: b.h,
            scope: b.scope || 'keep',
            identity: b.identity || undefined,
            tags: (b.tags && b.tags.length) ? b.tags : undefined
        })),
        face_tags: getSelectedFaceTags(),
        split: currentSplit
    };

    try {
        const response = await fetch(PAGE_DATA.saveUrl, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showStatus('Saved!', false);
            setTimeout(() => navigate('next'), 300);
        } else {
            const err = await response.json();
            showStatus('Error: ' + err.error, true);
        }
    } catch (e) {
        showStatus('Error: ' + e.message, true);
    }
}

function toggleFaceTag(tagName) {
    const checkbox = document.getElementById('face_tag_' + tagName);
    if (checkbox) checkbox.checked = !checkbox.checked;
}

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') return;

    if (e.key === 'n') { e.preventDefault(); toggleFaceTag('no_faces'); return; }
    if (e.key === 'l') { e.preventDefault(); toggleFaceTag('light_faces'); return; }

    if (e.key === 'ArrowLeft') navigate('prev');
    else if (e.key === 'ArrowRight') navigate('next');
    else if (e.key === 'Enter') { e.preventDefault(); save(); }
});

// --- Init canvas UI ---
const img = document.getElementById('photo');
const canvas = document.getElementById('canvas');

function startUI() {
    LabelingUI.init({
        mode: 'face',
        contentHash: contentHash,
        imgEl: img,
        canvasEl: canvas,
        onBoxesChanged: renderBoxList,
        onBoxSelected: onBoxSelected,
    });
    loadIdentities();
}

if (img.complete && img.naturalWidth) {
    startUI();
} else {
    img.addEventListener('load', startUI);
}
