"""Database helper module for bib number recognizer."""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from photo import compute_photo_hash, Photo

DB_PATH = Path(__file__).parent / "bibs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the database if needed."""
    db_exists = DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if not db_exists:
        init_database(conn)

    return conn


def init_database(conn: sqlite3.Connection) -> None:
    """Initialize the database with the schema."""
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()


def insert_photo(
    conn: sqlite3.Connection,
    album_url: str,
    photo_url: str,
    thumbnail_url: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> int:
    """Insert a photo record and return its ID. Returns existing ID if duplicate."""
    photo_hash = compute_photo_hash(photo_url)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO photos (photo_hash, album_url, photo_url, thumbnail_url, cache_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (photo_hash, album_url, photo_url, thumbnail_url, cache_path),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Photo already exists, return existing ID
        cursor.execute("SELECT id FROM photos WHERE photo_url = ?", (photo_url,))
        return cursor.fetchone()[0]


def update_photo_cache_path(
    conn: sqlite3.Connection,
    photo_id: int,
    cache_path: str,
) -> None:
    """Update the cache path for a photo."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE photos SET cache_path = ? WHERE id = ?",
        (cache_path, photo_id),
    )
    conn.commit()


def insert_bib_detection(
    conn: sqlite3.Connection,
    photo_id: int,
    bib_number: str,
    confidence: float,
    bbox: list,
) -> int:
    """Insert a bib detection record and return its ID."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bib_detections (photo_id, bib_number, confidence, bbox_json)
        VALUES (?, ?, ?, ?)
        """,
        (photo_id, bib_number, confidence, json.dumps(bbox)),
    )
    conn.commit()
    return cursor.lastrowid


def delete_bib_detections(conn: sqlite3.Connection, photo_id: int) -> int:
    """Delete all bib detections for a photo. Returns count of deleted rows."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bib_detections WHERE photo_id = ?", (photo_id,))
    conn.commit()
    return cursor.rowcount


def get_photos_by_bib(conn: sqlite3.Connection, bib_numbers: list[str]) -> list[dict]:
    """Get all photos containing any of the specified bib numbers."""
    placeholders = ",".join("?" * len(bib_numbers))
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT DISTINCT p.photo_hash, p.photo_url, p.thumbnail_url, p.album_url,
               GROUP_CONCAT(DISTINCT bd.bib_number) as matched_bibs
        FROM photos p
        JOIN bib_detections bd ON p.id = bd.photo_id
        WHERE bd.bib_number IN ({placeholders})
        GROUP BY p.id
        """,
        bib_numbers,
    )
    return [dict(row) for row in cursor.fetchall()]


def photo_exists(conn: sqlite3.Connection, photo_url: str) -> bool:
    """Check if a photo URL has already been scanned."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM photos WHERE photo_url = ?", (photo_url,))
    return cursor.fetchone() is not None


def get_photo_by_hash(conn: sqlite3.Connection, photo_hash: str) -> Optional[dict]:
    """Get a photo by its hash."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM photos WHERE photo_hash = ?", (photo_hash,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_photo_by_index(conn: sqlite3.Connection, index: int) -> Optional[dict]:
    """Get a photo by its 1-based index in the database order.

    Args:
        conn: Database connection
        index: 1-based index (e.g., 1 for first photo, 47 for 47th photo)

    Returns:
        Photo dict or None if index out of range
    """
    if index < 1:
        return None
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM photos ORDER BY id LIMIT 1 OFFSET ?", (index - 1,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_photo_count(conn: sqlite3.Connection) -> int:
    """Get the total number of photos in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    return cursor.fetchone()[0]


def migrate_add_photo_hash(conn: sqlite3.Connection) -> int:
    """Add photo_hash column to existing database and populate it. Returns count of migrated rows."""
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(photos)")
    columns = [row[1] for row in cursor.fetchall()]

    if "photo_hash" in columns:
        # Column exists, just ensure all rows have hashes
        cursor.execute("SELECT id, photo_url FROM photos WHERE photo_hash IS NULL OR photo_hash = ''")
        rows = cursor.fetchall()
        for row in rows:
            photo_hash = compute_photo_hash(row[1])
            cursor.execute("UPDATE photos SET photo_hash = ? WHERE id = ?", (photo_hash, row[0]))
        conn.commit()
        return len(rows)

    # Add column
    cursor.execute("ALTER TABLE photos ADD COLUMN photo_hash TEXT")

    # Populate hashes for all existing photos
    cursor.execute("SELECT id, photo_url FROM photos")
    rows = cursor.fetchall()
    for row in rows:
        photo_hash = compute_photo_hash(row[1])
        cursor.execute("UPDATE photos SET photo_hash = ? WHERE id = ?", (photo_hash, row[0]))

    # Create index
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_photo_hash ON photos(photo_hash)")

    conn.commit()
    return len(rows)
