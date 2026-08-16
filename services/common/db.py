"""SQLite state tracking for ingestion + wiki_writer. Never stores vault content."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_files (
    hash TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    drive_file_id TEXT,
    extracted_at TIMESTAMP,
    raw_path TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'pending',   -- pending | ok | failed
    extraction_error TEXT,
    wikified_at TIMESTAMP,                               -- NULL until wiki_writer processes it
    target_pages TEXT,                                   -- JSON array of vault paths it fed into
    review_resolution TEXT                                -- NULL | rejected | approved (set by resolve.py)
);

CREATE TABLE IF NOT EXISTS locks (
    job_name TEXT PRIMARY KEY,
    acquired_at TIMESTAMP NOT NULL,
    pid INTEGER
);

CREATE TABLE IF NOT EXISTS job_runs (
    job_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,          -- success | failure
    timestamp TIMESTAMP NOT NULL,
    files_processed INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);
"""


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def record_last_run(conn, job_name, status, timestamp, files_processed=0, detail=None):
    conn.execute(
        """
        INSERT INTO job_runs (job_name, status, timestamp, files_processed, detail)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_name) DO UPDATE SET
            status=excluded.status,
            timestamp=excluded.timestamp,
            files_processed=excluded.files_processed,
            detail=excluded.detail
        """,
        (job_name, status, timestamp, files_processed, detail),
    )
    conn.commit()


def upsert_raw_file(conn, hash_, source_filename, drive_file_id, extracted_at,
                     raw_path, extraction_status, extraction_error=None):
    conn.execute(
        """
        INSERT INTO raw_files (hash, source_filename, drive_file_id, extracted_at,
                                raw_path, extraction_status, extraction_error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hash) DO UPDATE SET
            source_filename=excluded.source_filename,
            drive_file_id=excluded.drive_file_id,
            extracted_at=excluded.extracted_at,
            raw_path=excluded.raw_path,
            extraction_status=excluded.extraction_status,
            extraction_error=excluded.extraction_error
        """,
        (hash_, source_filename, drive_file_id, extracted_at, raw_path,
         extraction_status, extraction_error),
    )
    conn.commit()


def hash_exists(conn, hash_):
    row = conn.execute("SELECT 1 FROM raw_files WHERE hash = ?", (hash_,)).fetchone()
    return row is not None


def get_unwikified(conn, limit):
    """Entries wiki_writer still needs to process -- both successful extractions
    (to be filed) and failed ones (to be flagged to _needs-review/ per SPEC.md
    Section 8), excluding anything the operator already rejected."""
    rows = conn.execute(
        """
        SELECT * FROM raw_files
        WHERE wikified_at IS NULL
          AND extraction_status IN ('ok', 'failed')
          AND (review_resolution IS NULL OR review_resolution != 'rejected')
        ORDER BY extracted_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows


def mark_wikified(conn, hash_, wikified_at, target_pages):
    conn.execute(
        "UPDATE raw_files SET wikified_at = ?, target_pages = ? WHERE hash = ?",
        (wikified_at, json.dumps(target_pages), hash_),
    )
    conn.commit()


def mark_review_resolution(conn, hash_, resolution):
    conn.execute(
        "UPDATE raw_files SET review_resolution = ? WHERE hash = ?",
        (resolution, hash_),
    )
    conn.commit()
