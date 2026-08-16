"""Operator-run cleanup for a test/mistaken ingestion, by content hash.

Removes a raw_files entry end-to-end:
  - raw/<hash>.json on disk
  - the vault/_needs-review/<hash>-*.md file, if wiki_writer flagged it
  - the vault/ page it wrote, if wiki_writer confidently filed it
    (only removed if target_pages recorded exactly one page and that
    page's content still traces back to this hash -- never blind-deletes
    a page that may have since been edited or hold other content)
  - the state.db row
  - commits + pushes the removal to GitHub

Does NOT touch the source file in Google Drive -- delete that yourself
in the Drive UI. Does NOT touch raw_files rows for OTHER hashes.

Usage (run on the machine/container that has the real VAULT_DATA_ROOT,
e.g. via Render's Shell tab against the live disk):
    python dev/cleanup_test_file.py <hash>
    python dev/cleanup_test_file.py <hash> --dry-run   # show what would happen, change nothing
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services"))

from common import db, git_ops
from common.paths import DATA_ROOT, VAULT_DIR, RAW_DIR, DB_PATH

REVIEW_DIR = VAULT_DIR / "_needs-review"


def find_review_file(hash_):
    matches = list(REVIEW_DIR.glob(f"{hash_}-*.md"))
    return matches[0] if matches else None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    hash_ = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    db.init_db(DB_PATH)
    with db.connect(DB_PATH) as conn:
        row = conn.execute("SELECT * FROM raw_files WHERE hash = ?", (hash_,)).fetchone()

    if row is None:
        print(f"no raw_files row found for hash {hash_} -- nothing to clean up in state.db")
    else:
        print(f"found row: source_filename={row['source_filename']!r}, "
              f"extraction_status={row['extraction_status']}, wikified_at={row['wikified_at']}")

    to_delete = []  # paths to remove from disk + stage for git rm

    raw_path = RAW_DIR / f"{hash_}.json"
    if raw_path.exists():
        to_delete.append(raw_path)

    review_path = find_review_file(hash_)
    if review_path is not None:
        to_delete.append(review_path)

    already_queued = {p.resolve() for p in to_delete}

    vault_page = None
    if row is not None and row["target_pages"]:
        target_pages = json.loads(row["target_pages"])
        # Only auto-delete if this hash produced exactly one page AND that
        # page still references this hash (superseded_raw frontmatter, or --
        # for the NEEDS_REVIEW case -- it's the review file already handled
        # above). A page that's since been overwritten by a later, unrelated
        # update must NOT be deleted just because this hash once fed into it.
        if len(target_pages) == 1:
            candidate = Path(target_pages[0])
            if not candidate.is_absolute():
                candidate = DATA_ROOT / candidate
            if candidate.exists() and candidate.resolve() not in already_queued:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                if hash_ in text:
                    vault_page = candidate
                    to_delete.append(candidate)
                else:
                    print(f"NOT auto-deleting {candidate} -- no longer references {hash_} "
                          f"(likely superseded by a later update). Leaving it in place.")

    if not to_delete and row is None:
        print("nothing found anywhere for this hash -- already clean, or hash is wrong")
        return

    print("\nwill remove:")
    for p in to_delete:
        print(f"  - {p}")
    if row is not None:
        print(f"  - state.db row for {hash_}")

    if dry_run:
        print("\n(dry run -- nothing changed)")
        return

    for p in to_delete:
        p.unlink()

    if row is not None:
        with db.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM raw_files WHERE hash = ?", (hash_,))
            conn.commit()
        print("removed state.db row")

    git_paths = [str(p) for p in to_delete]
    if git_paths:
        committed = git_ops.commit(DATA_ROOT, f"cleanup: remove test entry {hash_}", git_paths)
        if committed:
            git_ops.push(DATA_ROOT)
            print("committed + pushed removal to GitHub")
        else:
            print("nothing to commit (files were untracked or already gone from git)")

    print(f"\ndone. Remember to also delete the source file from the Google Drive folder yourself.")


if __name__ == "__main__":
    main()
