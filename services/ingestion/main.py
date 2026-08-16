"""ingestion: Drive -> raw/<hash>.json

Polls the Drive folder, hashes each file, skips anything already recorded
in state.db with a matching hash, runs the matching extractor, and writes
the result (or the failure) to raw/<hash>.json. Never silently drops a file
that fails extraction -- see SPEC.md Section 8.

Commits + pushes raw/ writes on its own cycle (independent of wiki_writer's
vault/ commits) so extracted content reaches GitHub quickly even when
wiki_writer runs on a much slower interval -- this lets you `git pull`
locally and inspect exactly what was extracted for debugging, without
waiting for wiki_writer to file it into the vault.

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

from common import db, lock, git_ops
from common.batch import BatchLimiter
from common.paths import DATA_ROOT, RAW_DIR, DB_PATH, bootstrap_git_repo
from ingestion import drive_client
from ingestion.extractors import get_extractor, ExtractionError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingestion")

JOB_NAME = "ingestion"
REPO_ROOT = DATA_ROOT  # the git working tree ingestion commits/pushes against

MAX_ITEMS_PER_RUN = int(os.environ.get("INGESTION_MAX_ITEMS", "20"))
MAX_SECONDS_PER_RUN = int(os.environ.get("INGESTION_MAX_SECONDS", "600"))  # 10 min
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
GIT_REMOTE_URL = os.environ.get("GIT_REMOTE_URL")  # e.g. https://<token>@github.com/<you>/raj-personal-vault.git


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
    """Returns the raw/<hash>.json path written, or None if the file was
    already processed (nothing new to commit)."""
    name = drive_file["name"]
    file_id = drive_file["id"]
    ext = Path(name).suffix.lower()

    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / name
        drive_client.download_file(service, file_id, str(local_path))
        hash_ = hash_bytes(local_path)

        if db.should_skip_ingestion(conn, hash_):
            log.info("skip (already processed): %s", name)
            return None

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

        return raw_path


def run():
    if not DRIVE_FOLDER_ID:
        raise RuntimeError("DRIVE_FOLDER_ID env var not set")

    bootstrap_git_repo()
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
                    raw_path = process_file(service, f, conn)
                    if raw_path is not None:
                        limiter.record()
                        processed += 1

                # Query (not the in-run written list) so this also retries any
                # entries from a prior run whose push failed -- e.g. the git
                # "dubious ownership" bug stranded successfully-extracted files
                # that were never pushed. Decoupled from extraction_status so a
                # git failure never permanently strands a file.
                pending = db.get_unpushed_raw_files(conn, limit=MAX_ITEMS_PER_RUN * 5)
                if pending and GIT_REMOTE_URL:
                    paths = [row["raw_path"] for row in pending]
                    try:
                        committed = git_ops.commit(
                            REPO_ROOT,
                            f"raw: {len(paths)} file(s) extracted",
                            paths,
                        )
                        if committed:
                            git_ops.push(REPO_ROOT)
                        # Mark pushed even if there was nothing new to commit
                        # (committed=False, already up to date) -- either way
                        # these files are now confirmed on the remote.
                        db.mark_git_pushed(
                            conn, [row["hash"] for row in pending],
                            datetime.now(timezone.utc).isoformat(),
                        )
                        log.info("committed + pushed %d raw file(s) to remote", len(paths))
                    except Exception:
                        # Local raw/ writes already succeeded and state.db already
                        # reflects them -- a commit/push failure here shouldn't fail
                        # the run; git_pushed_at stays NULL so the next run retries.
                        log.exception("commit/push of raw/ failed, will retry next run")
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

    return status


if __name__ == "__main__":
    if run() == "failure":
        sys.exit(1)
