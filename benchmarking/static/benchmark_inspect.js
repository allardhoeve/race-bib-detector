const photoResults = PAGE_DATA.photoResults;
const runId = PAGE_DATA.runId;
let currentIdx = PAGE_DATA.currentIdx;
let currentImageType = 'original';
let availableTabs = [];

// All possible tabs in order, with display names
const allTabs = [
    { key: 'original', label: 'Original', alwaysShow: true },
    { key: 'grayscale', label: 'Grayscale', alwaysShow: false },
    { key: 'clahe', label: 'CLAHE', alwaysShow: false },
    { key: 'resize', label: 'Resized', alwaysShow: false },
    { key: 'candidates', label: 'Candidates', alwaysShow: false },
    { key: 'detections', label: 'Detections', alwaysShow: false },
];

function updateTabs() {
    const result = photoResults[currentIdx];
    const artifacts = result.artifact_paths || {};
    const preprocess = result.preprocess_metadata || {};
    const steps = preprocess.steps || {};
    const claheStep = steps.clahe || {};
    const claheDeclined = claheStep.status === 'declined';

    const displayTabs = allTabs.filter(tab =>
        tab.alwaysShow || artifacts[tab.key] || (tab.key === 'clahe' && claheDeclined)
    );
    availableTabs = displayTabs
        .filter(tab => tab.alwaysShow || artifacts[tab.key])
        .map(tab => tab.key);

    // Render tabs
    const tabsContainer = document.getElementById('imageTabs');
    tabsContainer.innerHTML = displayTabs
        .map((tab) => {
            const hasArtifact = Boolean(artifacts[tab.key]);
            const isDeclined = tab.key === 'clahe' && claheDeclined && !hasArtifact;
            const isActive = tab.key === currentImageType;
            const shortcutIndex = availableTabs.indexOf(tab.key);
            const shortcut = shortcutIndex === -1 ? null : shortcutIndex + 1;
            const classes = [
                'image-tab',
                isActive ? 'active' : '',
                isDeclined ? 'declined' : '',
            ].filter(Boolean).join(' ');
            const claheMetrics = claheStep.metrics || {};
            const rangeValue = claheMetrics.dynamic_range ?? 'n/a';
            const thresholdValue = claheMetrics.threshold ?? 'n/a';
            const title = isDeclined
                ? `CLAHE declined (range=${rangeValue}, threshold=${thresholdValue})`
                : '';
            const onclick = isDeclined ? '' : `onclick="showImage('${tab.key}')"`;
            const disabled = isDeclined ? 'disabled' : '';
            const shortcutText = shortcut === null ? '' : ` <span style="color:#666;font-size:11px">(${shortcut})</span>`;
            const declinedText = isDeclined ? ' <span style="color:#555;font-size:11px">(declined)</span>' : '';
            return `<button class="${classes}" data-image="${tab.key}" ${onclick} ${disabled} title="${title}">${tab.label}${declinedText}${shortcutText}</button>`;
        }).join('');

    // If current image type is not available, switch to original
    if (!availableTabs.includes(currentImageType)) {
        currentImageType = 'original';
    }
}

function selectPhoto(idx) {
    if (idx < 0 || idx >= photoResults.length) return;
    currentIdx = idx;

    document.querySelectorAll('.photo-item').forEach((el, i) => {
        el.classList.toggle('active', i === idx);
    });

    document.getElementById('currentPos').textContent = idx + 1;
    document.getElementById('prevBtn').disabled = idx === 0;
    document.getElementById('nextBtn').disabled = idx === photoResults.length - 1;

    const activeItem = document.querySelector('.photo-item.active');
    if (activeItem) activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    updateTabs();
    updateDetails();
    updateImage();

    history.replaceState(null, '', `?filter=${document.getElementById('filter').value}&idx=${idx}`);
}

function updateDetails() {
    const result = photoResults[currentIdx];

    document.getElementById('detailStatus').innerHTML =
        `<span class="photo-status status-${result.status}">${result.status}</span>`;

    const expectedHtml = result.expected_bibs.map(bib => {
        const isMatch = result.detected_bibs.includes(bib);
        return `<span class="bib ${isMatch ? 'bib-tp' : 'bib-fn'}">${bib}</span>`;
    }).join('') || '<span style="color:#666">none</span>';
    document.getElementById('expectedBibs').innerHTML = expectedHtml;

    const detectedHtml = result.detected_bibs.map(bib => {
        const isMatch = result.expected_bibs.includes(bib);
        return `<span class="bib ${isMatch ? 'bib-tp' : 'bib-fp'}">${bib}</span>`;
    }).join('') || '<span style="color:#666">none</span>';
    document.getElementById('detectedBibs').innerHTML = detectedHtml;

    document.getElementById('detailCounts').textContent = `${result.tp} / ${result.fp} / ${result.fn}`;
    document.getElementById('detailTime').textContent = `${result.detection_time_ms.toFixed(0)}ms`;

    const tagsHtml = result.tags.map(tag => `<span class="tag">${tag}</span>`).join('') || '<span style="color:#666">none</span>';
    document.getElementById('detailTags').innerHTML = tagsHtml;

    const hashPrefix = result.content_hash.substring(0, 8);
    document.getElementById('editLink').href = PAGE_DATA.editLinkBase + hashPrefix + '?filter=all';
}

function updateImage() {
    const result = photoResults[currentIdx];
    const hash = result.content_hash;
    const hashPrefix = hash.substring(0, 8);

    let imagePath;
    if (currentImageType === 'original') {
        imagePath = PAGE_DATA.photoUrlTemplate.replace('HASH', hash);
    } else {
        imagePath = PAGE_DATA.artifactUrlTemplate
            .replace('RUN', runId)
            .replace('HASH', hashPrefix)
            .replace('TYPE', currentImageType);
    }
    document.getElementById('mainImage').src = imagePath;
}

function showImage(imageType) {
    currentImageType = imageType;
    document.querySelectorAll('.image-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.image === imageType);
    });
    updateImage();
}

function navigate(direction) {
    const newIdx = direction === 'prev' ? currentIdx - 1 : currentIdx + 1;
    if (newIdx >= 0 && newIdx < photoResults.length) selectPhoto(newIdx);
}

function applyFilter() {
    const filter = document.getElementById('filter').value;
    window.location.href = PAGE_DATA.inspectUrl + '?filter=' + filter;
}

function changeRun() {
    const newRunId = document.getElementById('runSelect').value;
    window.location.href = PAGE_DATA.benchmarkListUrl + newRunId + '/';
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') navigate('prev');
    else if (e.key === 'ArrowRight') navigate('next');
    else if (e.key >= '1' && e.key <= '9') {
        const idx = parseInt(e.key) - 1;
        if (idx < availableTabs.length) showImage(availableTabs[idx]);
    }
});

updateTabs();
updateDetails();
updateImage();
