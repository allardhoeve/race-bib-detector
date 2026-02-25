# Task 015: Refactor ensure_face_tables() — split DDL and migrations

Small focused refactor. Independent of all other pending tasks.

## Goal

`ensure_face_tables()` in `db.py:51–193` is 142 lines mixing DDL schema creation and
two legacy migration passes. Split into named helpers so each concern is testable and
inspectable on its own.

## Current structure (db.py:51–193)

```
ensure_face_tables(conn)
  ├── executescript: face_detections, face_clusters,
  │     face_cluster_members, bib_assignments DDL     lines  53–116
  ├── ALTER TABLE photos ADD COLUMN album_id          lines 118–119
  ├── ALTER TABLE face_clusters ADD COLUMN *          lines 121–128
  ├── executescript: albums table + indexes           lines 130–143
  ├── migration: photos.album_url → album_id         lines 145–169
  ├── migration: face_clusters.album_url → album_id  lines 171–187
  ├── sync albums from photos                         line  189–191
  └── conn.commit()                                   line  193
```

## Changes

Extract four private helpers and keep `ensure_face_tables()` as the coordinator:

### 1. `_create_face_tables(conn)` — lines 53–116

```python
def _create_face_tables(conn: sqlite3.Connection) -> None:
    """Create face_detections, face_clusters, face_cluster_members, bib_assignments."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS face_detections ( ... );
        ...
        CREATE TABLE IF NOT EXISTS bib_assignments ( ... );
        ...
    """)
```

### 2. `_ensure_album_columns(conn)` — lines 118–128

```python
def _ensure_album_columns(conn: sqlite3.Connection) -> None:
    """Add album_id / similarity columns if missing (idempotent ALTER TABLE)."""
    if not _column_exists(conn, "photos", "album_id"):
        conn.execute("ALTER TABLE photos ADD COLUMN album_id TEXT")
    if not _column_exists(conn, "face_clusters", "album_id"):
        conn.execute("ALTER TABLE face_clusters ADD COLUMN album_id TEXT")
    for col in ("avg_similarity", "min_similarity", "max_similarity"):
        if not _column_exists(conn, "face_clusters", col):
            conn.execute(f"ALTER TABLE face_clusters ADD COLUMN {col} REAL")
```

### 3. `_create_albums_table(conn)` — lines 130–143

```python
def _create_albums_table(conn: sqlite3.Connection) -> None:
    """Create albums table and its indexes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS albums ( ... );
        CREATE INDEX IF NOT EXISTS ...;
        CREATE INDEX IF NOT EXISTS ...;
    """)
```

### 4. `_migrate_album_urls(conn)` — lines 145–191

```python
def _migrate_album_urls(conn: sqlite3.Connection) -> None:
    """Migrate legacy album_url columns to album_id (one-time migration, idempotent)."""
    if _column_exists(conn, "photos", "album_url"):
        # ... (current lines 146–169)
    if _column_exists(conn, "face_clusters", "album_url"):
        # ... (current lines 172–187)
    conn.execute(
        "INSERT OR IGNORE INTO albums (album_id) "
        "SELECT DISTINCT album_id FROM photos WHERE album_id IS NOT NULL"
    )
```

### 5. Slim down `ensure_face_tables()`

```python
def ensure_face_tables(conn: sqlite3.Connection) -> None:
    """Ensure face + album tables exist for legacy databases."""
    _create_face_tables(conn)
    _ensure_album_columns(conn)
    _create_albums_table(conn)
    _migrate_album_urls(conn)
    conn.commit()
```

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md).

- Run `pytest tests/` — all DB tests should pass unchanged.
- The helpers are private (`_` prefix) and not tested directly; `ensure_face_tables()`
  is the tested entry point.

## Scope boundaries

- **In scope**: splitting the function body into helpers. No SQL changes.
- **Out of scope**: changing the schema, migration logic, or any column definitions.
