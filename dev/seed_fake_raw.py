"""Dev-only helper: seed state.db + raw/ with a fake extracted entry so you
can run wiki_writer end-to-end without live Google Drive access.

Requires ANTHROPIC_API_KEY to be set (wiki_writer's decision step is a real
model call). Does NOT require GOOGLE_SERVICE_ACCOUNT_JSON, DRIVE_FOLDER_ID,
or GIT_REMOTE_URL.

Usage:
    python dev/seed_fake_raw.py
    python services/wiki_writer/main.py
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

FAKE_CONTENT = """Auto Insurance Policy
Provider: SafeDrive Insurance
Policy Number: SD-2026-88213
Named Insured: Raj
Vehicle: 2022 Honda Civic
Coverage Period: 2026-01-01 to 2027-01-01
Premium: $1,240/year
"""


def main():
    db.init_db(DB_PATH)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    hash_ = hashlib.sha256(FAKE_CONTENT.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "source_filename": "auto-insurance-2026.pdf",
        "extracted_at": now,
        "content": FAKE_CONTENT,
        "extraction_status": "ok",
    }
    raw_path = RAW_DIR / f"{hash_}.json"
    raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with db.connect(DB_PATH) as conn:
        db.upsert_raw_file(conn, hash_, "auto-insurance-2026.pdf", "fake-drive-id", now, str(raw_path), "ok")

    print(f"seeded raw entry: {hash_}")
    print(f"raw file: {raw_path}")
    print("now run: python services/wiki_writer/main.py")


if __name__ == "__main__":
    main()
