"""wiki_writer: raw/ -> vault/*.md

Queries state.db for raw entries where wikified_at IS NULL, decides
CONFIDENT_UPDATE / NEW_INFO / NEEDS_REVIEW per entry (see decision.py and
SPEC.md Section 4), writes/updates vault/ and commits to git, or writes to
vault/_needs-review/ for anything ambiguous (SPEC.md Section 5).

Bounded batch per run + lock backstop -- same discipline as ingestion.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import db, lock
from common.batch import BatchLimiter
from common.paths import DATA_ROOT, VAULT_DIR, DB_PATH, bootstrap_git_repo
from wiki_writer import decision, git_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wiki_writer")

JOB_NAME = "wiki_writer"
REPO_ROOT = DATA_ROOT  # the git working tree wiki_writer commits/pushes against
REVIEW_DIR = VAULT_DIR / "_needs-review"

MAX_ITEMS_PER_RUN = int(os.environ.get("WIKI_WRITER_MAX_ITEMS", "20"))
MAX_SECONDS_PER_RUN = int(os.environ.get("WIKI_WRITER_MAX_SECONDS", "600"))  # 10 min
GIT_REMOTE_URL = os.environ.get("GIT_REMOTE_URL")  # e.g. https://<token>@github.com/<you>/raj-personal-vault.git


def _slug(filename, n=40):
    import re
    base = re.sub(r"[^a-z0-9]+", "-", filename.lower()).strip("-")
    return base[:n] or "entry"


def write_needs_review(raw_row, decision_result):
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    hash_ = raw_row["hash"]
    slug = _slug(raw_row["source_filename"])
    out_path = REVIEW_DIR / f"{hash_}-{slug}.md"

    raw_content = json.loads(Path(raw_row["raw_path"]).read_text(encoding="utf-8"))["content"] or ""

    frontmatter = (
        "---\n"
        f"raw_hash: {hash_}\n"
        f"source_filename: {raw_row['source_filename']}\n"
        f"flagged_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"reason: \"{decision_result['reason']}\"\n"
        f"candidate_target: {decision_result['target_page']}\n"
        f"confidence: {decision_result['confidence']}\n"
        "---\n\n"
    )
    body = (
        "## Extracted content\n"
        f"{raw_content}\n\n"
        "## What the agent would have done\n"
        f"{decision_result['draft_content']}\n"
    )
    out_path.write_text(frontmatter + body, encoding="utf-8")
    return out_path


def write_extraction_failure_review(raw_row):
    """Failed extractions also route to _needs-review/, per SPEC.md Section 8."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    hash_ = raw_row["hash"]
    slug = _slug(raw_row["source_filename"])
    out_path = REVIEW_DIR / f"{hash_}-{slug}.md"

    frontmatter = (
        "---\n"
        f"raw_hash: {hash_}\n"
        f"source_filename: {raw_row['source_filename']}\n"
        f"flagged_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"reason: \"extraction failed: {raw_row['extraction_error']}\"\n"
        "candidate_target: (none -- extraction failed)\n"
        "confidence: low\n"
        "---\n\n"
        "## Extracted content\n"
        "(extraction failed, no content available)\n\n"
        "## What the agent would have done\n"
        "(nothing -- resolve manually, e.g. re-upload an unprotected/uncorrupted version)\n"
    )
    out_path.write_text(frontmatter, encoding="utf-8")
    return out_path


def apply_write(target_page_rel, draft_content):
    target_path = REPO_ROOT / target_page_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(draft_content, encoding="utf-8")
    return target_path


def process_entry(raw_row, conn):
    hash_ = raw_row["hash"]

    if raw_row["extraction_status"] == "failed":
        review_path = write_extraction_failure_review(raw_row)
        git_ops.commit(REPO_ROOT, f"flag: extraction failure for {raw_row['source_filename']}", [str(review_path)])
        db.mark_wikified(conn, hash_, datetime.now(timezone.utc).isoformat(), [str(review_path)])
        log.info("flagged extraction failure: %s", raw_row["source_filename"])
        return

    raw_content = json.loads(Path(raw_row["raw_path"]).read_text(encoding="utf-8"))["content"] or ""
    candidates = decision.find_candidate_pages(VAULT_DIR, raw_row["source_filename"], raw_content)
    result = decision.decide(raw_content, raw_row["source_filename"], candidates, VAULT_DIR)

    now = datetime.now(timezone.utc).isoformat()

    if result["outcome"] in ("CONFIDENT_UPDATE", "NEW_INFO"):
        content = result["draft_content"]
        if result["outcome"] == "CONFIDENT_UPDATE":
            content = (
                "---\n"
                f"last_updated: {now}\n"
                f"superseded_raw: {hash_}\n"
                "---\n\n" + content
            )
        target_path = apply_write(result["target_page"], content)
        git_ops.commit(
            REPO_ROOT,
            f"{result['outcome'].lower()}: {result['target_page']} from {raw_row['source_filename']}",
            [str(target_path)],
        )
        db.mark_wikified(conn, hash_, now, [result["target_page"]])
        log.info("%s -> %s", result["outcome"], result["target_page"])

    else:  # NEEDS_REVIEW
        review_path = write_needs_review(raw_row, result)
        git_ops.commit(REPO_ROOT, f"flag: needs review for {raw_row['source_filename']}", [str(review_path)])
        db.mark_wikified(conn, hash_, now, [str(review_path.relative_to(REPO_ROOT))])
        log.info("NEEDS_REVIEW -> %s", review_path.name)


def run():
    bootstrap_git_repo()
    db.init_db(DB_PATH)
    status = "success"
    processed = 0
    detail = None

    with db.connect(DB_PATH) as conn:
        try:
            with lock.job_lock(conn, JOB_NAME, expected_runtime_seconds=MAX_SECONDS_PER_RUN):
                limiter = BatchLimiter(MAX_ITEMS_PER_RUN, MAX_SECONDS_PER_RUN)
                entries = db.get_unwikified(conn, MAX_ITEMS_PER_RUN)
                log.info("found %d unwikified entries", len(entries))

                for row in entries:
                    if not limiter.should_continue():
                        log.info("batch limit reached, checkpointing and exiting")
                        break
                    try:
                        process_entry(row, conn)
                        limiter.record()
                        processed += 1
                    except Exception:
                        log.exception("failed to process entry %s, leaving for next run", row["hash"])

                if processed and GIT_REMOTE_URL:
                    try:
                        git_ops.push(REPO_ROOT)
                        log.info("pushed %d commit(s) to remote", processed)
                    except Exception:
                        # Local commits already succeeded -- they're the real audit
                        # trail. A push failure shouldn't fail the whole run; the
                        # next successful run's push will catch up on the backlog.
                        log.exception("push to remote failed, will retry next run")
        except lock.LockHeldError as e:
            status = "skipped"
            detail = str(e)
            log.warning("skipping run: %s", e)
        except Exception as e:
            status = "failure"
            detail = str(e)
            log.exception("wiki_writer run failed")
        finally:
            db.record_last_run(
                conn, JOB_NAME, status, datetime.now(timezone.utc).isoformat(), processed, detail
            )

    return status


if __name__ == "__main__":
    if run() == "failure":
        sys.exit(1)
