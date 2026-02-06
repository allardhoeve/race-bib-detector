-- Photos table
-- Draft: facial recognition schema additions are included here for now.
-- See schema_v2.sql for a consolidated draft schema snapshot.
CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_hash TEXT NOT NULL UNIQUE,  -- 8-char hash derived from photo_url, stable identifier
    album_id TEXT NOT NULL,
    photo_url TEXT NOT NULL UNIQUE,
    thumbnail_url TEXT,
    cache_path TEXT,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast hash lookups
CREATE INDEX idx_photo_hash ON photos(photo_hash);
CREATE INDEX idx_photo_album_id ON photos(album_id);

-- Albums (metadata only; no raw directory paths)
CREATE TABLE albums (
    album_id TEXT PRIMARY KEY,
    label TEXT,
    source_type TEXT,
    source_hint TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bib detections (one photo can have multiple bibs)
CREATE TABLE bib_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    bib_number TEXT NOT NULL,
    confidence REAL,
    bbox_json TEXT,  -- JSON: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);

-- Index for fast bib lookups
CREATE INDEX idx_bib_number ON bib_detections(bib_number);

-- Face detections (one photo can have multiple faces)
CREATE TABLE face_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    face_index INTEGER NOT NULL,
    bbox_json TEXT NOT NULL,  -- JSON: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    snippet_path TEXT,        -- cropped face snippet file path
    preview_path TEXT,        -- precomputed boxed preview path
    embedding BLOB,           -- raw embedding bytes
    embedding_dim INTEGER,
    model_name TEXT,
    model_version TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    UNIQUE(photo_id, face_index)
);

CREATE INDEX idx_face_detections_photo_id ON face_detections(photo_id);

-- Face clusters (scoped per album/event)
CREATE TABLE face_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id TEXT NOT NULL,
    model_name TEXT,
    model_version TEXT,
    centroid BLOB,
    centroid_dim INTEGER,
    size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_face_clusters_album_id ON face_clusters(album_id);

-- Face cluster membership
CREATE TABLE face_cluster_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    face_id INTEGER NOT NULL,
    distance REAL,
    FOREIGN KEY (cluster_id) REFERENCES face_clusters(id),
    FOREIGN KEY (face_id) REFERENCES face_detections(id),
    UNIQUE(cluster_id, face_id)
);

CREATE INDEX idx_face_cluster_members_cluster_id ON face_cluster_members(cluster_id);
CREATE INDEX idx_face_cluster_members_face_id ON face_cluster_members(face_id);

-- Bib assignments (resolved bib tags with provenance)
CREATE TABLE bib_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id INTEGER NOT NULL,
    bib_number TEXT NOT NULL,
    source TEXT NOT NULL,     -- bib-detection | face-inherited
    confidence REAL,
    evidence_json TEXT,       -- JSON: face_id, cluster_id, similarity, bbox, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);

CREATE INDEX idx_bib_assignments_photo_id ON bib_assignments(photo_id);
CREATE INDEX idx_bib_assignments_bib_number ON bib_assignments(bib_number);
