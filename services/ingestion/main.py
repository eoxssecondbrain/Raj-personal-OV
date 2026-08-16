"""ingestion: Drive -> raw/<hash>.json

Polls the Drive folder, hashes each file, skips anything already recorded
in state.db with a matching hash, runs the matching extractor, and writes
the result (or the failure) to raw/<hash>.json. Never silently drops a file
that fails extraction -- see SPEC.md Section 8.

Bounded batch per run + lock backstop -- see SPEC.md Section 7.
"""
import hashlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import db, lock
from common.batch import BatchLimiter
from ingestion import drive_client
from ingestion.extractors import get_extractor, ExtractionError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingestion")

JOB_NAME = "ingestion"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "raw"
DB_PATH = REPO_ROOT / "state.db"

MAX_ITEMS_PER_RUN = int(os.environ.get("INGESTION_MAX_ITEMS", "20"))
MAX_SECONDS_PER_RUN = int(os.environ.get("INGESTION_MAX_SECONDS", "600"))  # 10 min
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")


def hash_bytes(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_raw(hash_, payload):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{hash_}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def process_file(service, drive_file, conn):
    name = drive_file["name"]
    file_id = drive_file["id"]
    ext = Path(name).suffix.lower()

    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / name
        drive_client.download_file(service, file_id, str(local_path))
        hash_ = hash_bytes(local_path)

        if db.hash_exists(conn, hash_):
            log.info("skip (already processed): %s", name)
            return False

        now = datetime.now(timezone.utc).isoformat()

        try:
            extractor = get_extractor(ext)
            result = extractor(str(local_path))

            if isinstance(result, dict):  # image extractor: two-pass result
                payload = {
                    "source_filename": name,
                    "extracted_at": now,
                    "content": result["content"],
                    "extraction_status": "ok",
                    "image_classification": result["classification"],
                    "image_classification_reason": result["reason"],
                }
            else:
                payload = {
                    "source_filename": name,
                    "extracted_at": now,
                    "content": result,
                    "extraction_status": "ok",
                }

            raw_path = write_raw(hash_, payload)
            db.upsert_raw_file(conn, hash_, name, file_id, now, str(raw_path), "ok")
            log.info("extracted: %s -> %s", name, raw_path.name)

        except ExtractionError as e:
            payload = {
                "source_filename": name,
                "extracted_at": now,
                "content": None,
                "extraction_status": "failed",
                "error": str(e),
            }
            raw_path = write_raw(hash_, payload)
            db.upsert_raw_file(conn, hash_, name, file_id, now, str(raw_path), "failed", str(e))
            log.warning("extraction failed: %s (%s)", name, e)

        return True


def run():
    if not DRIVE_FOLDER_ID:
        raise RuntimeError("DRIVE_FOLDER_ID env var not set")

    db.init_db(DB_PATH)
    status = "success"
    processed = 0
    detail = None

    with db.connect(DB_PATH) as conn:
        try:
            with lock.job_lock(conn, JOB_NAME, expected_runtime_seconds=MAX_SECONDS_PER_RUN):
                service = drive_client.get_service()
                files = drive_client.list_folder_files(service, DRIVE_FOLDER_ID)
                log.info("found %d files in Drive folder", len(files))

                limiter = BatchLimiter(MAX_ITEMS_PER_RUN, MAX_SECONDS_PER_RUN)
                for f in files:
                    if not limiter.should_continue():
                        log.info("batch limit reached, checkpointing and exiting")
                        break
                    did_work = process_file(service, f, conn)
                    if did_work:
                        limiter.record()
                        processed += 1
        except lock.LockHeldError as e:
            status = "skipped"
            detail = str(e)
            log.warning("skipping run: %s", e)
        except Exception as e:
            status = "failure"
            detail = str(e)
            log.exception("ingestion run failed")
        finally:
            db.record_last_run(
                conn, JOB_NAME, status, datetime.now(timezone.utc).isoformat(), processed, detail
            )

    if status == "failure":
        sys.exit(1)


if __name__ == "__main__":
    run()
