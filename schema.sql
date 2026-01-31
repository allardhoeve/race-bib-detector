-- Photos table
CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_hash TEXT NOT NULL UNIQUE,  -- 8-char hash derived from photo_url, stable identifier
    album_url TEXT NOT NULL,
    photo_url TEXT NOT NULL UNIQUE,
    thumbnail_url TEXT,
    cache_path TEXT,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast hash lookups
CREATE INDEX idx_photo_hash ON photos(photo_hash);

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
