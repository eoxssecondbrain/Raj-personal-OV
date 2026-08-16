"""Dev-only helper: seed a fake extraction-failure entry, to smoke-test the
_needs-review/ path and resolve.py without needing a real corrupted file.

Usage:
    python dev/seed_fake_review.py
    python services/wiki_writer/main.py
    # then inspect vault/_needs-review/, and try:
    python services/wiki_writer/resolve.py reject <hash-printed-above>
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services"))

from common import db

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw"
DB_PATH = REPO_ROOT / "state.db"


def main():
    db.init_db(DB_PATH)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fake_bytes = b"fake corrupted pdf bytes for testing"
    hash_ = hashlib.sha256(fake_bytes).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    error = "password-protected PDF"

    payload = {
        "source_filename": "locked-document.pdf",
        "extracted_at": now,
        "content": None,
        "extraction_status": "failed",
        "error": error,
    }
    raw_path = RAW_DIR / f"{hash_}.json"
    raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with db.connect(DB_PATH) as conn:
        db.upsert_raw_file(conn, hash_, "locked-document.pdf", "fake-drive-id", now, str(raw_path), "failed", error)

    print(f"seeded failed-extraction entry: {hash_}")
    print("now run: python services/wiki_writer/main.py")


if __name__ == "__main__":
    main()
