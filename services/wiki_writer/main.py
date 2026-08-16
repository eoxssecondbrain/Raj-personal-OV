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

from common import db, lock, git_ops
from common.batch import BatchLimiter
from common.paths import DATA_ROOT, VAULT_DIR, DB_PATH, bootstrap_git_repo
from wiki_writer import decision

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
    """Writes the decided content and marks wikified_at immediately -- no git
    call here. A git failure must never prevent mark_wikified from running,
    since the content write is what actually matters; git commit/push for the
    whole batch happens once in run(), after every entry in the batch has
    already been written and marked (see run() below and the git_ops.push
    retry-until-success pattern shared with ingestion).

    Returns the path written (str), for run() to batch into one commit.
    """
    hash_ = raw_row["hash"]

    if raw_row["extraction_status"] == "failed":
        review_path = write_extraction_failure_review(raw_row)
        db.mark_wikified(conn, hash_, datetime.now(timezone.utc).isoformat(), [str(review_path)])
        log.info("flagged extraction failure: %s", raw_row["source_filename"])
        return str(review_path)

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
        # target_pages stores the absolute written path (not the vault-relative
        # display path) so get_unpushed_wiki_writes() can reconstruct exactly
        # what to `git add` on a later retry.
        db.mark_wikified(conn, hash_, now, [str(target_path)])
        log.info("%s -> %s", result["outcome"], result["target_page"])
        return str(target_path)

    else:  # NEEDS_REVIEW
        review_path = write_needs_review(raw_row, result)
        db.mark_wikified(conn, hash_, now, [str(review_path)])
        log.info("NEEDS_REVIEW -> %s", review_path.name)
        return str(review_path)


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

                # Query (not just this run's writes) so this also retries any
                # entries from a prior run whose commit/push failed -- same
                # stranding bug ingestion had, and the reason wikified_at no
                # longer implies "reached GitHub."
                pending = db.get_unpushed_wiki_writes(conn, limit=MAX_ITEMS_PER_RUN * 5)
                if pending and GIT_REMOTE_URL:
                    paths = [json.loads(row["target_pages"])[0] for row in pending]
                    try:
                        committed = git_ops.commit(
                            REPO_ROOT,
                            f"wiki_writer: {len(paths)} entries",
                            paths,
                        )
                        if committed:
                            git_ops.push(REPO_ROOT)
                        db.mark_wiki_git_pushed(
                            conn, [row["hash"] for row in pending],
                            datetime.now(timezone.utc).isoformat(),
                        )
                        log.info("committed + pushed %d wiki write(s) to remote", len(paths))
                    except Exception:
                        # Local writes + mark_wikified already succeeded --
                        # wiki_git_pushed_at stays NULL so the next run retries
                        # just the git step, same pattern as ingestion.
                        log.exception("commit/push of vault/ writes failed, will retry next run")
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
