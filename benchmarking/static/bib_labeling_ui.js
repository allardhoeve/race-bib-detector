let currentSplit = PAGE_DATA.split;
const contentHash = PAGE_DATA.contentHash;

function getSelectedTags() {
    return Array.from(document.querySelectorAll('input[name="tags"]:checked'))
                .map(cb => cb.value);
}

function onSplitClick(split) {
    currentSplit = split;
    setSplit(split);
}

// --- Box list rendering ---
function renderBoxList(boxes) {
    const list = document.getElementById('boxList');
    list.innerHTML = '';
    boxes.forEach((box, i) => {
        const li = document.createElement('li');
        li.className = 'box-item' + (i === LabelingUI.getState().selectedIdx ? ' selected' : '');
        li.innerHTML = '<span class="box-label">' +
            (box.number || '?') + ' [' + (box.scope || 'bib') + ']</span>' +
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
}

function onBoxSelected(idx, box) {
    const editor = document.getElementById('boxEditor');
    if (idx < 0 || !box) {
        editor.classList.remove('visible');
        return;
    }
    editor.classList.add('visible');
    document.getElementById('boxNumber').value = box.number || '';
    const radios = document.querySelectorAll('input[name="boxScope"]');
    radios.forEach(r => { r.checked = r.value === (box.scope || 'bib'); });

    // Update box list selection
    document.querySelectorAll('.box-item').forEach((el, i) => {
        el.classList.toggle('selected', i === idx);
    });

    // Focus number input
    document.getElementById('boxNumber').focus();
}

// Update box when editor changes
document.getElementById('boxNumber').addEventListener('input', function() {
    const state = LabelingUI.getState();
    if (state.selectedIdx >= 0) {
        state.boxes[state.selectedIdx].number = this.value;
        renderBoxList(state.boxes);
        LabelingUI.render();
    }
});

document.querySelectorAll('input[name="boxScope"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const state = LabelingUI.getState();
        if (state.selectedIdx >= 0) {
            state.boxes[state.selectedIdx].scope = this.value;
            renderBoxList(state.boxes);
            LabelingUI.render();
        }
    });
});

// --- Save ---
async function save() {
    const state = LabelingUI.getState();
    const data = {
        content_hash: contentHash,
        boxes: state.boxes.map(b => ({
            x: b.x, y: b.y, w: b.w, h: b.h,
            number: b.number || '',
            scope: b.scope || 'bib'
        })),
        tags: getSelectedTags(),
        split: currentSplit
    };

    try {
        const response = await fetch(PAGE_DATA.saveUrl, {
            method: 'POST',
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

function navigate(direction) {
    const prevUrl = PAGE_DATA.prevUrl;
    const nextUrl = PAGE_DATA.nextUrl;
    const url = direction === 'prev' ? prevUrl : nextUrl;
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

function toggleTag(tagName) {
    const checkbox = document.getElementById('tag_' + tagName);
    if (checkbox) checkbox.checked = !checkbox.checked;
}

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') return;

    if (e.key === 'o') { e.preventDefault(); toggleTag('obscured_bib'); return; }
    if (e.key === 'n') { e.preventDefault(); toggleTag('no_bib'); return; }
    if (e.key === 'b') { e.preventDefault(); toggleTag('blurry_bib'); return; }

    if (e.key === 'ArrowLeft') navigate('prev');
    else if (e.key === 'ArrowRight') navigate('next');
    else if (e.key === 'Enter') { e.preventDefault(); save(); }
});

// --- Init canvas UI ---
const img = document.getElementById('photo');
const canvas = document.getElementById('canvas');

function startUI() {
    LabelingUI.init({
        mode: 'bib',
        contentHash: contentHash,
        imgEl: img,
        canvasEl: canvas,
        onBoxesChanged: renderBoxList,
        onBoxSelected: onBoxSelected,
    });
}

if (img.complete && img.naturalWidth) {
    startUI();
} else {
    img.addEventListener('load', startUI);
}
