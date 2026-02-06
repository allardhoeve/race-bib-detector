"""
HTML templates for the web interface.

Templates are stored as string constants to keep the application self-contained.
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bib Scanner - Photo {{ current }} of {{ total }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            padding: 20px 0 30px;
        }

        .header-links {
            margin-top: 10px;
            display: flex;
            gap: 12px;
            justify-content: center;
        }

        .header-link {
            color: #64ffda;
            text-decoration: none;
            font-size: 0.9rem;
            border-bottom: 1px dashed rgba(100, 255, 218, 0.6);
        }

        .header-link:hover {
            color: #9fffe4;
            border-bottom-color: #9fffe4;
        }

        h1 {
            font-size: 1.8rem;
            font-weight: 600;
            color: #fff;
            margin-bottom: 8px;
        }

        .subtitle {
            color: #8892b0;
            font-size: 1rem;
        }

        .main-content {
            display: flex;
            gap: 30px;
            align-items: flex-start;
        }

        .image-section {
            flex: 1;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .image-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }

        .image-tab {
            flex: 1;
            padding: 12px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #8892b0;
            cursor: pointer;
            text-align: center;
            font-size: 0.9rem;
            transition: all 0.2s;
        }

        .image-tab:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .image-tab.active {
            background: rgba(100, 255, 218, 0.15);
            border-color: #64ffda;
            color: #64ffda;
        }

        .image-container {
            position: relative;
            width: 100%;
            border-radius: 12px;
            overflow: hidden;
            background: #0a0a0a;
        }

        .image-container img {
            width: 100%;
            height: auto;
            display: block;
        }

        .image-view {
            display: none;
        }

        .image-view.active {
            display: block;
        }

        .snippets-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            padding: 20px;
            justify-content: center;
            background: #0a0a0a;
            min-height: 200px;
        }

        .faces-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            padding: 20px;
            background: #0a0a0a;
            min-height: 200px;
        }

        .face-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 10px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: transform 0.2s, border-color 0.2s;
        }

        .face-card:hover {
            transform: scale(1.04);
            border-color: #64ffda;
        }

        .face-card img {
            width: 100%;
            border-radius: 8px;
            display: block;
        }

        .face-label {
            margin-top: 8px;
            font-size: 0.8rem;
            color: #8892b0;
        }

        .snippet-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: transform 0.2s, border-color 0.2s;
        }

        .snippet-card:hover {
            transform: scale(1.05);
            border-color: #64ffda;
        }

        .snippet-card img {
            max-width: 200px;
            max-height: 150px;
            border-radius: 8px;
            display: block;
            margin: 0 auto;
        }

        .snippet-label {
            margin-top: 10px;
            font-size: 1.5rem;
            font-weight: 700;
            color: #64ffda;
        }

        .snippet-conf {
            font-size: 0.9rem;
            font-weight: 400;
            color: #8892b0;
        }

        .candidates-legend {
            display: flex;
            justify-content: center;
            gap: 24px;
            padding: 12px;
            background: rgba(0, 0, 0, 0.5);
            font-size: 0.85rem;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .legend-passed {
            color: #4ade80;
        }

        .legend-rejected {
            color: #f87171;
        }

        .sidebar {
            width: 320px;
            flex-shrink: 0;
        }

        .bib-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }

        .bib-card h2 {
            font-size: 1rem;
            color: #8892b0;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 16px;
        }

        .bib-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .bib-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.08);
            padding: 16px 20px;
            border-radius: 12px;
            transition: transform 0.2s, background 0.2s;
        }

        .bib-item:hover {
            transform: translateX(4px);
            background: rgba(255, 255, 255, 0.12);
        }

        .bib-number {
            font-size: 2rem;
            font-weight: 700;
            color: #64ffda;
        }

        .confidence {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }

        .confidence-label {
            font-size: 0.75rem;
            color: #8892b0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .confidence-value {
            font-size: 1.25rem;
            font-weight: 600;
        }

        .confidence-high { color: #64ffda; }
        .confidence-medium { color: #ffd93d; }
        .confidence-low { color: #ff6b6b; }

        .confidence-bar {
            width: 80px;
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            margin-top: 6px;
            overflow: hidden;
        }

        .confidence-fill {
            height: 100%;
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        .no-bibs {
            text-align: center;
            padding: 30px;
            color: #8892b0;
        }

        .no-bibs-icon {
            font-size: 3rem;
            margin-bottom: 12px;
            opacity: 0.5;
        }

        .navigation {
            display: flex;
            gap: 12px;
        }

        .nav-btn {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 16px 24px;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
        }

        .nav-btn-prev {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }

        .nav-btn-prev:hover:not(.disabled) {
            background: rgba(255, 255, 255, 0.2);
        }

        .nav-btn-next {
            background: #64ffda;
            color: #1a1a2e;
        }

        .nav-btn-next:hover:not(.disabled) {
            background: #4ad4b5;
            transform: translateY(-2px);
        }

        .nav-btn.disabled {
            opacity: 0.3;
            cursor: not-allowed;
            pointer-events: none;
        }

        .nav-arrow {
            font-size: 1.2rem;
        }

        .photo-info {
            margin-top: 16px;
            padding: 16px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            font-size: 0.85rem;
            color: #8892b0;
        }

        .photo-info-row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
        }

        .photo-info-label {
            color: #5a6480;
        }

        .keyboard-hint {
            text-align: center;
            margin-top: 20px;
            padding: 12px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 8px;
            font-size: 0.8rem;
            color: #5a6480;
        }

        kbd {
            display: inline-block;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            font-family: monospace;
            margin: 0 4px;
        }

        @media (max-width: 900px) {
            .main-content {
                flex-direction: column;
            }

            .sidebar {
                width: 100%;
            }
        }
        
        h1 a {
            text-decoration: none;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><a href="/">Bib Number Scanner</a></h1>
            <p class="subtitle">Photo {{ current }} of {{ total }}</p>
            <div class="header-links">
                <a class="header-link" href="/faces">Face Clusters</a>
            </div>
        </header>

        <div class="main-content">
            <div class="image-section">
                {% if photo.cache_filename %}
                <div class="image-tabs">
                    <div class="image-tab active" onclick="showImage('original')">Original</div>
                    <div class="image-tab {% if not photo.has_candidates %}disabled{% endif %}" onclick="showImage('candidates')" {% if not photo.has_candidates %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Candidates {% if not photo.has_candidates %}(none){% endif %}
                    </div>
                    <div class="image-tab {% if not photo.has_face_candidates %}disabled{% endif %}" onclick="showImage('face-candidates')" {% if not photo.has_face_candidates %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Face Candidates {% if not photo.has_face_candidates %}(none){% endif %}
                    </div>
                    <div class="image-tab {% if not photo.has_gray_bbox %}disabled{% endif %}" onclick="showImage('bbox')" {% if not photo.has_gray_bbox %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Detections {% if not photo.has_gray_bbox %}(none){% endif %}
                    </div>
                    <div class="image-tab {% if not photo.has_snippets %}disabled{% endif %}" onclick="showImage('snippets')" {% if not photo.has_snippets %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Snippets {% if not photo.has_snippets %}(none){% endif %}
                    </div>
                    <div class="image-tab {% if not photo.has_faces %}disabled{% endif %}" onclick="showImage('faces')" {% if not photo.has_faces %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Faces {% if not photo.has_faces %}(none){% endif %}
                    </div>
                </div>
                {% endif %}

                <div class="image-container">
                    <div id="view-original" class="image-view active">
                        {% if photo.original_url %}
                        <img src="{{ photo.original_url }}" alt="Photo {{ current }}">
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>Cached original not available</p>
                        </div>
                        {% endif %}
                    </div>
                    <div id="view-candidates" class="image-view">
                        {% if photo.has_candidates %}
                        <img src="/cache/candidates/{{ photo.cache_filename }}" alt="Photo {{ current }} with candidates">
                        <div class="candidates-legend">
                            <span class="legend-item legend-passed">● Passed</span>
                            <span class="legend-item legend-rejected">● Rejected</span>
                        </div>
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No candidates image available</p>
                            <p style="margin-top: 10px; font-size: 0.8rem;">Rescan this photo to generate candidates visualization</p>
                        </div>
                        {% endif %}
                    </div>
                    <div id="view-face-candidates" class="image-view">
                        {% if photo.has_face_candidates %}
                        <img src="/cache/faces/candidates/{{ photo.cache_filename }}" alt="Photo {{ current }} with face candidates">
                        <div class="candidates-legend">
                            <span class="legend-item legend-passed">● Passed</span>
                            <span class="legend-item legend-rejected">● Rejected</span>
                        </div>
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No face candidates image available</p>
                            <p style="margin-top: 10px; font-size: 0.8rem;">Rescan this photo to generate face candidates visualization</p>
                        </div>
                        {% endif %}
                    </div>
                    <div id="view-bbox" class="image-view">
                        {% if photo.has_gray_bbox %}
                        <img src="/cache/gray_bounding/{{ photo.cache_filename }}" alt="Photo {{ current }} with bounding boxes">
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No bounding box image available</p>
                        </div>
                        {% endif %}
                    </div>
                    <div id="view-snippets" class="image-view">
                        {% if photo.has_snippets %}
                        <div class="snippets-grid">
                            {% for bib in bibs %}
                            {% if bib.snippet_filename %}
                            <div class="snippet-card">
                                <img src="/cache/snippets/{{ bib.snippet_filename }}" alt="Bib {{ bib.bib_number }}">
                                <div class="snippet-label">{{ bib.bib_number }} <span class="snippet-conf">({{ "%.0f"|format(bib.confidence * 100) }}%)</span></div>
                            </div>
                            {% endif %}
                            {% endfor %}
                        </div>
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No snippets available</p>
                        </div>
                        {% endif %}
                    </div>
                    <div id="view-faces" class="image-view">
                        {% if photo.has_faces %}
                        <div class="faces-grid">
                            {% for face in faces %}
                            {% if face.snippet_filename %}
                            <div class="face-card">
                                <img src="/cache/faces/snippets/{{ face.snippet_filename }}" alt="Face {{ face.face_index }}">
                                <div class="face-label">Face {{ face.face_index }}</div>
                            </div>
                            {% endif %}
                            {% endfor %}
                        </div>
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No faces detected</p>
                        </div>
                        {% endif %}
                    </div>
                </div>

                <div class="photo-info">
                    <div class="photo-info-row">
                        <span class="photo-info-label">Photo Hash</span>
                        <span style="font-family: monospace; color: #64ffda;">{{ photo.photo_hash }}</span>
                    </div>
                    <div class="photo-info-row">
                        <span class="photo-info-label">Scanned</span>
                        <span>{{ photo.scanned_at or 'Unknown' }}</span>
                    </div>
                </div>
            </div>

            <div class="sidebar">
                <div class="bib-card">
                    <h2>Detected Bibs</h2>
                    {% if bibs %}
                    <div class="bib-list">
                        {% for bib in bibs %}
                        <div class="bib-item">
                            <span class="bib-number">{{ bib.bib_number }}</span>
                            <div class="confidence">
                                <span class="confidence-label">Confidence</span>
                                <span class="confidence-value {% if bib.confidence >= 0.8 %}confidence-high{% elif bib.confidence >= 0.5 %}confidence-medium{% else %}confidence-low{% endif %}">
                                    {{ "%.0f"|format(bib.confidence * 100) }}%
                                </span>
                                <div class="confidence-bar">
                                    <div class="confidence-fill {% if bib.confidence >= 0.8 %}confidence-high{% elif bib.confidence >= 0.5 %}confidence-medium{% else %}confidence-low{% endif %}"
                                         style="width: {{ bib.confidence * 100 }}%; background: currentColor;"></div>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% else %}
                    <div class="no-bibs">
                        <div class="no-bibs-icon">🏃</div>
                        <p>No bib numbers detected</p>
                    </div>
                    {% endif %}
                </div>

                <div class="navigation">
                    <a href="/photo/{{ prev_hash }}" class="nav-btn nav-btn-prev {% if not has_prev %}disabled{% endif %}">
                        <span class="nav-arrow">←</span>
                        <span>Previous</span>
                    </a>
                    <a href="/photo/{{ next_hash }}" class="nav-btn nav-btn-next {% if not has_next %}disabled{% endif %}">
                        <span>Next</span>
                        <span class="nav-arrow">→</span>
                    </a>
                </div>

                <div class="keyboard-hint">
                    <kbd>←</kbd> <kbd>→</kbd> navigate &nbsp;|&nbsp; <kbd>O</kbd> original &nbsp;|&nbsp; <kbd>C</kbd> candidates &nbsp;|&nbsp; <kbd>A</kbd> face candidates &nbsp;|&nbsp; <kbd>D</kbd> detections &nbsp;|&nbsp; <kbd>S</kbd> snippets &nbsp;|&nbsp; <kbd>F</kbd> faces
                </div>
            </div>
        </div>
    </div>

    <script>
        function showImage(view) {
            // Don't switch to unavailable views
            if (view === 'candidates' && !{{ 'true' if photo.has_candidates else 'false' }}) {
                return;
            }
            if (view === 'face-candidates' && !{{ 'true' if photo.has_face_candidates else 'false' }}) {
                return;
            }
            if (view === 'bbox' && !{{ 'true' if photo.has_gray_bbox else 'false' }}) {
                return;
            }
            if (view === 'snippets' && !{{ 'true' if photo.has_snippets else 'false' }}) {
                return;
            }
            if (view === 'faces' && !{{ 'true' if photo.has_faces else 'false' }}) {
                return;
            }

            // Update tabs
            document.querySelectorAll('.image-tab').forEach(tab => tab.classList.remove('active'));
            const tabIndex = {'original': 0, 'candidates': 1, 'face-candidates': 2, 'bbox': 3, 'snippets': 4, 'faces': 5}[view];
            const tabs = document.querySelectorAll('.image-tab');
            if (tabs[tabIndex]) tabs[tabIndex].classList.add('active');

            // Update views
            document.querySelectorAll('.image-view').forEach(v => v.classList.remove('active'));
            document.getElementById('view-' + view).classList.add('active');
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowLeft' && {{ 'true' if has_prev else 'false' }}) {
                window.location.href = '/photo/{{ prev_hash }}';
            } else if (e.key === 'ArrowRight' && {{ 'true' if has_next else 'false' }}) {
                window.location.href = '/photo/{{ next_hash }}';
            } else if (e.key === 'o' || e.key === 'O') {
                // Return to original view with 'o' key
                showImage('original');
            } else if (e.key === 'c' || e.key === 'C') {
                // Toggle candidates view with 'c' key
                if ({{ 'true' if photo.has_candidates else 'false' }}) {
                    if (document.getElementById('view-candidates').classList.contains('active')) {
                        showImage('original');
                    } else {
                        showImage('candidates');
                    }
                }
            } else if (e.key === 'a' || e.key === 'A') {
                // Toggle face candidates view with 'a' key
                if ({{ 'true' if photo.has_face_candidates else 'false' }}) {
                    if (document.getElementById('view-face-candidates').classList.contains('active')) {
                        showImage('original');
                    } else {
                        showImage('face-candidates');
                    }
                }
            } else if (e.key === 'd' || e.key === 'D') {
                // Toggle detections/bbox view with 'd' key
                if ({{ 'true' if photo.has_gray_bbox else 'false' }}) {
                    if (document.getElementById('view-bbox').classList.contains('active')) {
                        showImage('original');
                    } else {
                        showImage('bbox');
                    }
                }
            } else if (e.key === 's' || e.key === 'S') {
                // Toggle snippets view with 's' key
                if ({{ 'true' if photo.has_snippets else 'false' }}) {
                    if (document.getElementById('view-snippets').classList.contains('active')) {
                        showImage('original');
                    } else {
                        showImage('snippets');
                    }
                }
            } else if (e.key === 'f' || e.key === 'F') {
                if ({{ 'true' if photo.has_faces else 'false' }}) {
                    if (document.getElementById('view-faces').classList.contains('active')) {
                        showImage('original');
                    } else {
                        showImage('faces');
                    }
                }
            }
        });
    </script>
</body>
</html>
"""

EMPTY_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bib Scanner - No Photos</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
        }
        .message {
            text-align: center;
            padding: 40px;
        }
        .icon {
            font-size: 4rem;
            margin-bottom: 20px;
            opacity: 0.5;
        }
        h1 {
            font-size: 1.5rem;
            margin-bottom: 12px;
        }
        p {
            color: #8892b0;
        }
        code {
            display: block;
            margin-top: 20px;
            padding: 16px 24px;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="message">
        <div class="icon">📷</div>
        <h1>No Photos Scanned Yet</h1>
        <p>Run the scanner first to add photos to the database.</p>
        <code>python bnr.py scan &lt;directory&gt; --album-label "Example"</code>
    </div>
</body>
</html>
"""

FACE_CLUSTERS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bib Scanner - Face Clusters</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
        }
        header {
            text-align: center;
            padding: 16px 0 24px;
        }
        h1 {
            font-size: 1.8rem;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #8892b0;
        }
        .section {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }
        .cluster-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
        }
        .cluster-card {
            background: rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 16px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .cluster-title {
            font-weight: 600;
            color: #64ffda;
        }
        .cluster-meta {
            margin-top: 8px;
            font-size: 0.85rem;
            color: #8892b0;
        }
        .faces-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 14px;
            margin-top: 12px;
        }
        .face-card {
            background: rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 8px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .face-card img {
            width: 100%;
            border-radius: 8px;
            display: block;
        }
        .face-label {
            margin-top: 6px;
            font-size: 0.75rem;
            color: #8892b0;
        }
        a.link {
            color: #64ffda;
            text-decoration: none;
        }
        a.link:hover {
            color: #9fffe4;
        }
        .empty {
            padding: 24px;
            text-align: center;
            color: #8892b0;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Face Clusters</h1>
            <p class="subtitle">Read-only inspection view</p>
            <p><a class="link" href="/">Back to photos</a></p>
        </header>

        <div class="section">
            <h2 style="margin-bottom: 12px;">Clusters</h2>
            {% if clusters %}
            <div class="cluster-list">
                {% for cluster in clusters %}
                <div class="cluster-card">
                    <div class="cluster-title">Cluster {{ cluster.id }}</div>
                    <div class="cluster-meta">Album: {{ cluster.album_label or cluster.album_id }}</div>
                    <div class="cluster-meta">Model: {{ cluster.model_name }} {{ cluster.model_version }}</div>
                    <div class="cluster-meta">Size: {{ cluster.size or 0 }}</div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty">No clusters yet (run clustering).</div>
            {% endif %}
        </div>

        <div class="section">
            <h2 style="margin-bottom: 12px;">Unclustered Faces</h2>
            {% if unclustered_faces %}
            <div class="faces-grid">
                {% for face in unclustered_faces %}
                <div class="face-card">
                    {% if face.snippet_filename %}
                    <a class="link" href="/photo/{{ face.photo_hash }}">
                        <img src="/cache/faces/snippets/{{ face.snippet_filename }}" alt="Face {{ face.face_index }}">
                    </a>
                    {% else %}
                    <div class="empty">No snippet</div>
                    {% endif %}
                    <div class="face-label">Photo {{ face.photo_hash }}</div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty">No unclustered faces found.</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""
