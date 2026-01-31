"""Database helper module for bib number recognizer."""

import json
import sqlite3
from pathlib import Path
from typing import Optional

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
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO photos (album_url, photo_url, thumbnail_url, cache_path)
            VALUES (?, ?, ?, ?)
            """,
            (album_url, photo_url, thumbnail_url, cache_path),
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


def get_photos_by_bib(conn: sqlite3.Connection, bib_numbers: list[str]) -> list[dict]:
    """Get all photos containing any of the specified bib numbers."""
    placeholders = ",".join("?" * len(bib_numbers))
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT DISTINCT p.id, p.photo_url, p.thumbnail_url, p.album_url,
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
