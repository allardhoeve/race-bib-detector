"""Database helper module for bib number recognizer."""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from photo import compute_photo_hash
from faces.types import FaceBbox, FaceModelInfo, embedding_to_bytes

if TYPE_CHECKING:
    import numpy as np

DB_PATH = Path(__file__).parent / "bibs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def compute_album_id(source: str) -> str:
    """Compute a short album identifier from a source string."""
    return hashlib.sha256(source.encode()).hexdigest()[:8]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the database if needed."""
    db_exists = DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if not db_exists:
        init_database(conn)
    else:
        ensure_face_tables(conn)

    return conn


def init_database(conn: sqlite3.Connection) -> None:
    """Initialize the database with the schema."""
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()


def ensure_face_tables(conn: sqlite3.Connection) -> None:
    """Ensure face + album tables exist for legacy databases."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS face_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            face_index INTEGER NOT NULL,
            bbox_json TEXT NOT NULL,
            snippet_path TEXT,
            preview_path TEXT,
            embedding BLOB,
            embedding_dim INTEGER,
            model_name TEXT,
            model_version TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id),
            UNIQUE(photo_id, face_index)
        );

        CREATE INDEX IF NOT EXISTS idx_face_detections_photo_id ON face_detections(photo_id);

        CREATE TABLE IF NOT EXISTS face_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id TEXT NOT NULL,
            model_name TEXT,
            model_version TEXT,
            centroid BLOB,
            centroid_dim INTEGER,
            size INTEGER,
            avg_similarity REAL,
            min_similarity REAL,
            max_similarity REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS face_cluster_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER NOT NULL,
            face_id INTEGER NOT NULL,
            distance REAL,
            FOREIGN KEY (cluster_id) REFERENCES face_clusters(id),
            FOREIGN KEY (face_id) REFERENCES face_detections(id),
            UNIQUE(cluster_id, face_id)
        );

        CREATE INDEX IF NOT EXISTS idx_face_cluster_members_cluster_id
            ON face_cluster_members(cluster_id);
        CREATE INDEX IF NOT EXISTS idx_face_cluster_members_face_id
            ON face_cluster_members(face_id);

        CREATE TABLE IF NOT EXISTS bib_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            bib_number TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL,
            evidence_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );

        CREATE INDEX IF NOT EXISTS idx_bib_assignments_photo_id ON bib_assignments(photo_id);
        CREATE INDEX IF NOT EXISTS idx_bib_assignments_bib_number ON bib_assignments(bib_number);
        """
    )

    if not _column_exists(conn, "photos", "album_id"):
        conn.execute("ALTER TABLE photos ADD COLUMN album_id TEXT")

    if not _column_exists(conn, "face_clusters", "album_id"):
        conn.execute("ALTER TABLE face_clusters ADD COLUMN album_id TEXT")
    if not _column_exists(conn, "face_clusters", "avg_similarity"):
        conn.execute("ALTER TABLE face_clusters ADD COLUMN avg_similarity REAL")
    if not _column_exists(conn, "face_clusters", "min_similarity"):
        conn.execute("ALTER TABLE face_clusters ADD COLUMN min_similarity REAL")
    if not _column_exists(conn, "face_clusters", "max_similarity"):
        conn.execute("ALTER TABLE face_clusters ADD COLUMN max_similarity REAL")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS albums (
            album_id TEXT PRIMARY KEY,
            label TEXT,
            source_type TEXT,
            source_hint TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_photo_album_id ON photos(album_id);
        CREATE INDEX IF NOT EXISTS idx_face_clusters_album_id ON face_clusters(album_id);
        """
    )

    if _column_exists(conn, "photos", "album_url"):
        conn.execute(
            """
            UPDATE photos
            SET album_id = COALESCE(album_id, ?)
            WHERE album_id IS NULL AND album_url IS NOT NULL
            """,
            (compute_album_id("legacy"),),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT album_url FROM photos WHERE album_url IS NOT NULL")
        for (album_url,) in cursor.fetchall():
            album_id = compute_album_id(album_url)
            conn.execute(
                """
                UPDATE photos
                SET album_id = ?
                WHERE album_url = ? AND (album_id IS NULL OR album_id = ?)
                """,
                (album_id, album_url, compute_album_id("legacy")),
            )
            conn.execute(
                "INSERT OR IGNORE INTO albums (album_id, source_type) VALUES (?, ?)",
                (album_id, "legacy"),
            )

    if _column_exists(conn, "face_clusters", "album_url"):
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT album_url FROM face_clusters WHERE album_url IS NOT NULL")
        for (album_url,) in cursor.fetchall():
            album_id = compute_album_id(album_url)
            conn.execute(
                """
                UPDATE face_clusters
                SET album_id = ?
                WHERE album_url = ? AND (album_id IS NULL OR album_id = '')
                """,
                (album_id, album_url),
            )
            conn.execute(
                "INSERT OR IGNORE INTO albums (album_id, source_type) VALUES (?, ?)",
                (album_id, "legacy"),
            )

    conn.execute(
        "INSERT OR IGNORE INTO albums (album_id) SELECT DISTINCT album_id FROM photos WHERE album_id IS NOT NULL"
    )

    conn.commit()


def insert_photo(
    conn: sqlite3.Connection,
    album_id: str,
    photo_url: str,
    thumbnail_url: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> int:
    """Insert a photo record and return its ID. Returns existing ID if duplicate."""
    photo_hash = compute_photo_hash(photo_url)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(photos)")
    columns = {row[1] for row in cursor.fetchall()}

    insert_columns = ["photo_hash", "photo_url", "thumbnail_url", "cache_path"]
    insert_values = [photo_hash, photo_url, thumbnail_url, cache_path]

    if "album_id" in columns:
        insert_columns.insert(1, "album_id")
        insert_values.insert(1, album_id)

    if "album_url" in columns:
        insert_columns.insert(1, "album_url")
        insert_values.insert(1, album_id)

    placeholders = ", ".join("?" for _ in insert_columns)
    columns_sql = ", ".join(insert_columns)

    try:
        if _column_exists(conn, "albums", "album_id"):
            conn.execute("INSERT OR IGNORE INTO albums (album_id) VALUES (?)", (album_id,))
        cursor.execute(
            f"""
            INSERT INTO photos ({columns_sql})
            VALUES ({placeholders})
            """,
            insert_values,
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


def ensure_album(
    conn: sqlite3.Connection,
    album_id: str,
    label: Optional[str] = None,
    source_type: Optional[str] = None,
    source_hint: Optional[str] = None,
) -> None:
    """Ensure an album record exists and update metadata when provided."""
    conn.execute(
        """
        INSERT OR IGNORE INTO albums (album_id, label, source_type, source_hint)
        VALUES (?, ?, ?, ?)
        """,
        (album_id, label, source_type, source_hint),
    )
    if label or source_type or source_hint:
        conn.execute(
            """
            UPDATE albums
            SET label = COALESCE(?, label),
                source_type = COALESCE(?, source_type),
                source_hint = COALESCE(?, source_hint)
            WHERE album_id = ?
            """,
            (label, source_type, source_hint, album_id),
        )
    conn.commit()


def list_albums(conn: sqlite3.Connection) -> list[dict]:
    """List all albums with photo counts."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.album_id,
               a.label,
               a.source_type,
               a.source_hint,
               a.created_at,
               COUNT(p.id) AS photo_count
        FROM albums a
        LEFT JOIN photos p ON p.album_id = a.album_id
        GROUP BY a.album_id
        ORDER BY a.created_at DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def forget_album(conn: sqlite3.Connection, album_id: str) -> dict:
    """Delete all records for an album. Returns counts of deleted rows."""
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM photos WHERE album_id = ?", (album_id,))
    photo_ids = [row[0] for row in cursor.fetchall()]

    counts = {
        "bib_detections": 0,
        "face_detections": 0,
        "bib_assignments": 0,
        "photos": 0,
        "face_cluster_members": 0,
        "face_clusters": 0,
        "albums": 0,
    }

    if photo_ids:
        placeholders = ",".join("?" for _ in photo_ids)
        cursor.execute(
            f"DELETE FROM bib_detections WHERE photo_id IN ({placeholders})",
            photo_ids,
        )
        counts["bib_detections"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM face_detections WHERE photo_id IN ({placeholders})",
            photo_ids,
        )
        counts["face_detections"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM bib_assignments WHERE photo_id IN ({placeholders})",
            photo_ids,
        )
        counts["bib_assignments"] = cursor.rowcount

        cursor.execute(
            f"DELETE FROM photos WHERE id IN ({placeholders})",
            photo_ids,
        )
        counts["photos"] = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM face_cluster_members
        WHERE cluster_id IN (SELECT id FROM face_clusters WHERE album_id = ?)
        """,
        (album_id,),
    )
    counts["face_cluster_members"] = cursor.rowcount

    cursor.execute("DELETE FROM face_clusters WHERE album_id = ?", (album_id,))
    counts["face_clusters"] = cursor.rowcount

    cursor.execute("DELETE FROM albums WHERE album_id = ?", (album_id,))
    counts["albums"] = cursor.rowcount

    conn.commit()
    return counts


def list_cache_entries(conn: sqlite3.Connection) -> list[dict]:
    """List photo hashes and cache paths for all photos."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT photo_hash, cache_path
        FROM photos
        WHERE cache_path IS NOT NULL
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def list_album_cache_entries(conn: sqlite3.Connection, album_id: str) -> list[dict]:
    """List photo hashes and cache paths for a specific album."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT photo_hash, cache_path
        FROM photos
        WHERE album_id = ?
          AND cache_path IS NOT NULL
        """,
        (album_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


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


def insert_face_detection(
    conn: sqlite3.Connection,
    photo_id: int,
    face_index: int,
    bbox: FaceBbox,
    embedding: "np.ndarray | None",
    model_info: FaceModelInfo,
    snippet_path: Optional[str] = None,
    preview_path: Optional[str] = None,
) -> int:
    """Insert a face detection record and return its ID."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO face_detections (
            photo_id, face_index, bbox_json, snippet_path, preview_path,
            embedding, embedding_dim, model_name, model_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            photo_id,
            face_index,
            json.dumps(bbox),
            snippet_path,
            preview_path,
            embedding_to_bytes(embedding) if embedding is not None else None,
            model_info.embedding_dim,
            model_info.name,
            model_info.version,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def delete_face_detections(conn: sqlite3.Connection, photo_id: int) -> int:
    """Delete all face detections for a photo. Returns count of deleted rows."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM face_detections WHERE photo_id = ?", (photo_id,))
    conn.commit()
    return cursor.rowcount


def list_face_embeddings_for_album(conn: sqlite3.Connection, album_id: str) -> list[dict]:
    """List face embeddings for an album, including model metadata."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fd.id,
               fd.embedding,
               fd.embedding_dim,
               fd.model_name,
               fd.model_version
        FROM face_detections fd
        JOIN photos p ON p.id = fd.photo_id
        WHERE p.album_id = ?
          AND fd.embedding IS NOT NULL
        ORDER BY fd.id
        """,
        (album_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def delete_face_clusters_for_album_model(
    conn: sqlite3.Connection,
    album_id: str,
    model_name: str,
    model_version: str,
) -> dict:
    """Delete face clusters and members for a specific album + model."""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM face_cluster_members
        WHERE cluster_id IN (
            SELECT id FROM face_clusters
            WHERE album_id = ? AND model_name = ? AND model_version = ?
        )
        """,
        (album_id, model_name, model_version),
    )
    members_deleted = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM face_clusters
        WHERE album_id = ? AND model_name = ? AND model_version = ?
        """,
        (album_id, model_name, model_version),
    )
    clusters_deleted = cursor.rowcount
    conn.commit()
    return {
        "face_cluster_members": members_deleted,
        "face_clusters": clusters_deleted,
    }


def insert_face_cluster(
    conn: sqlite3.Connection,
    album_id: str,
    model_name: str,
    model_version: str,
    centroid: "np.ndarray",
    avg_similarity: float,
    min_similarity: float,
    max_similarity: float,
    size: int,
) -> int:
    """Insert a face cluster record and return its ID."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO face_clusters (
            album_id, model_name, model_version,
            centroid, centroid_dim, size,
            avg_similarity, min_similarity, max_similarity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            album_id,
            model_name,
            model_version,
            embedding_to_bytes(centroid),
            centroid.size,
            size,
            avg_similarity,
            min_similarity,
            max_similarity,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def insert_face_cluster_member(
    conn: sqlite3.Connection,
    cluster_id: int,
    face_id: int,
    distance: float,
) -> int:
    """Insert a face cluster member record and return its ID."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO face_cluster_members (cluster_id, face_id, distance)
        VALUES (?, ?, ?)
        """,
        (cluster_id, face_id, distance),
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
        SELECT DISTINCT p.photo_hash, p.photo_url, p.thumbnail_url, p.album_id,
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


def get_photo_id_by_url(conn: sqlite3.Connection, photo_url: str) -> Optional[int]:
    """Get a photo ID by its URL."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM photos WHERE photo_url = ?", (photo_url,))
    row = cursor.fetchone()
    return row[0] if row else None


def face_detections_exist(conn: sqlite3.Connection, photo_id: int) -> bool:
    """Check if a photo already has face detections."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM face_detections WHERE photo_id = ? LIMIT 1", (photo_id,))
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
