"""Operator-run CLI for triaging vault/_needs-review/. NOT scheduled, NOT exposed via MCP.

Usage:
    python resolve.py approve <hash>
    python resolve.py reject <hash>

approve: moves the review file's "What the agent would have done" section into
  the real target page (candidate_target frontmatter), deletes the review file,
  commits.
edit-then-approve: operator edits the review file's "What the agent would have
  done" section by hand first, then runs approve -- same command either way.
reject: deletes the review file, records resolution=rejected in state.db so an
  identical future re-flag of the same source doesn't recur.
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import db, git_ops
from common.paths import DATA_ROOT, VAULT_DIR, DB_PATH

REPO_ROOT = DATA_ROOT
REVIEW_DIR = VAULT_DIR / "_needs-review"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n\n", re.DOTALL)
DRAFT_SECTION_RE = re.compile(r"## What the agent would have done\n(.*)", re.DOTALL)


def find_review_file(hash_):
    matches = list(REVIEW_DIR.glob(f"{hash_}-*.md"))
    if not matches:
        raise FileNotFoundError(f"no review file found for hash {hash_}")
    if len(matches) > 1:
        raise RuntimeError(f"multiple review files match hash {hash_}: {matches}")
    return matches[0]


def parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("review file missing frontmatter")
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"')
    return fields, text[m.end():]


def extract_draft(body):
    m = DRAFT_SECTION_RE.search(body)
    if not m:
        raise ValueError("review file missing 'What the agent would have done' section")
    return m.group(1).strip()


def approve(hash_):
    review_path = find_review_file(hash_)
    text = review_path.read_text(encoding="utf-8")
    fields, body = parse_frontmatter(text)

    target = fields.get("candidate_target")
    if not target or target.startswith("(none"):
        print(f"cannot approve: no candidate_target set for {hash_} (likely an extraction failure -- resolve manually)")
        return

    draft = extract_draft(body)
    target_path = REPO_ROOT / target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(draft, encoding="utf-8")
    review_path.unlink()

    git_ops.commit(
        REPO_ROOT,
        f"resolved: {hash_} by operator, action=approve",
        [str(target_path), str(review_path)],
    )
    git_ops.push(REPO_ROOT)

    with db.connect(DB_PATH) as conn:
        db.mark_review_resolution(conn, hash_, "approved")

    print(f"approved: {hash_} -> {target}")


def reject(hash_):
    review_path = find_review_file(hash_)
    review_path.unlink()

    with db.connect(DB_PATH) as conn:
        db.mark_review_resolution(conn, hash_, "rejected")

    git_ops.commit(
        REPO_ROOT,
        f"resolved: {hash_} by operator, action=reject",
        [str(review_path)],
    )
    git_ops.push(REPO_ROOT)
    print(f"rejected: {hash_}")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("approve", "reject"):
        print(__doc__)
        sys.exit(1)

    action, hash_ = sys.argv[1], sys.argv[2]
    db.init_db(DB_PATH)

    if action == "approve":
        approve(hash_)
    else:
        reject(hash_)


if __name__ == "__main__":
    main()
