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
    review_resolution TEXT,                               -- NULL | rejected | approved (set by resolve.py)
    git_pushed_at TIMESTAMP,                              -- NULL until raw/<hash>.json reached GitHub
    wiki_git_pushed_at TIMESTAMP                          -- NULL until wiki_writer's vault/_needs-review write reached GitHub
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


def _ensure_column(conn, table, column, coltype):
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        # Migrate existing databases created before git_pushed_at existed --
        # CREATE TABLE IF NOT EXISTS above is a no-op on an existing table,
        # so the column has to be added explicitly for pre-existing state.db
        # files. Existing rows get NULL, which correctly means "needs retry."
        _ensure_column(conn, "raw_files", "git_pushed_at", "TIMESTAMP")
        _ensure_column(conn, "raw_files", "wiki_git_pushed_at", "TIMESTAMP")
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


def should_skip_ingestion(conn, hash_):
    """True if this file has already been successfully extracted, OR has
    already failed AND wiki_writer has already flagged that failure to
    _needs-review/ (wikified_at is set even for failed entries -- see
    wiki_writer.main.process_entry). A failed extraction that wiki_writer
    hasn't reached yet is retried on the next ingestion run instead of being
    stuck forever -- e.g. a bug in an extractor getting fixed shouldn't
    require manually clearing state.db to reprocess. Once wiki_writer has
    flagged it, the operator's review file is authoritative; ingestion must
    not silently retry underneath it.
    """
    row = conn.execute(
        "SELECT extraction_status, wikified_at FROM raw_files WHERE hash = ?", (hash_,)
    ).fetchone()
    if row is None:
        return False
    if row["extraction_status"] == "ok":
        return True
    if row["extraction_status"] == "failed" and row["wikified_at"] is not None:
        return True
    return False


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


def get_unpushed_raw_files(conn, limit):
    """Successfully extracted files whose raw/<hash>.json hasn't reached
    GitHub yet -- either brand new from this run, or left over from a prior
    run whose commit/push failed (e.g. the git ownership bug). Retried every
    run until push actually succeeds, decoupled from extraction_status so a
    git failure never permanently strands a file."""
    rows = conn.execute(
        """
        SELECT * FROM raw_files
        WHERE extraction_status = 'ok' AND git_pushed_at IS NULL
        ORDER BY extracted_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows


def mark_git_pushed(conn, hashes, pushed_at):
    if not hashes:
        return
    placeholders = ",".join("?" * len(hashes))
    conn.execute(
        f"UPDATE raw_files SET git_pushed_at = ? WHERE hash IN ({placeholders})",
        (pushed_at, *hashes),
    )
    conn.commit()


def mark_wikified(conn, hash_, wikified_at, target_pages):
    conn.execute(
        "UPDATE raw_files SET wikified_at = ?, target_pages = ? WHERE hash = ?",
        (wikified_at, json.dumps(target_pages), hash_),
    )
    conn.commit()


def get_unpushed_wiki_writes(conn, limit):
    """Entries wiki_writer has already written to vault/ (target_pages set)
    but whose commit/push hasn't succeeded yet -- either brand new from this
    run, or stranded by a prior git failure. Mirrors get_unpushed_raw_files:
    decoupled from wikified_at so a git failure never permanently strands a
    vault write the way the pre-fix code did (see the flagged-but-never-
    committed _needs-review file this replaced)."""
    rows = conn.execute(
        """
        SELECT * FROM raw_files
        WHERE wikified_at IS NOT NULL AND wiki_git_pushed_at IS NULL
        ORDER BY wikified_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows


def mark_wiki_git_pushed(conn, hashes, pushed_at):
    if not hashes:
        return
    placeholders = ",".join("?" * len(hashes))
    conn.execute(
        f"UPDATE raw_files SET wiki_git_pushed_at = ? WHERE hash IN ({placeholders})",
        (pushed_at, *hashes),
    )
    conn.commit()


def mark_review_resolution(conn, hash_, resolution):
    conn.execute(
        "UPDATE raw_files SET review_resolution = ? WHERE hash = ?",
        (resolution, hash_),
    )
    conn.commit()
