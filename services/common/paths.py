"""Single source of truth for where vault/, raw/, and state.db live on disk.

On Render, the code checkout is NOT persistent across deploys -- only the
mounted disk is. DATA_ROOT points at that disk's mount path (e.g. /var/data),
set via the VAULT_DATA_ROOT env var in infra/vault.render.yaml, and IS itself
the git working tree that wiki_writer commits/pushes against -- see
bootstrap_git_repo() below and MANUAL_SETUP.md Section 5. This avoids having
two separate copies of vault/ (one in the ephemeral checkout, one on disk)
that could drift.

Locally, DATA_ROOT defaults to the repo root so `python services/ingestion/main.py`
etc. just work against this working tree directly without extra setup --
there's no separate "code checkout" vs "data disk" distinction in dev.
"""
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Local dev convenience: load repo_root/.env if present. No-op on Render
# (no .env file is deployed there; env vars are set directly on the service).
# Plain `source .env` in a shell breaks on the multi-line/JSON-valued vars
# here (GOOGLE_SERVICE_ACCOUNT_JSON), so python-dotenv is the supported path.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

DATA_ROOT = Path(os.environ.get("VAULT_DATA_ROOT", str(REPO_ROOT)))

VAULT_DIR = DATA_ROOT / "vault"
RAW_DIR = DATA_ROOT / "raw"
DB_PATH = DATA_ROOT / "state.db"


def bootstrap_git_repo():
    """On first boot against a fresh/empty persistent disk, clone the vault's
    GitHub remote into DATA_ROOT so it becomes the git working tree. No-op if
    DATA_ROOT is already a git repo (normal case on every boot after the first),
    and no-op locally where DATA_ROOT == REPO_ROOT (already a git repo you manage
    yourself).
    """
    if DATA_ROOT == REPO_ROOT:
        return
    if (DATA_ROOT / ".git").exists():
        return

    remote_url = os.environ.get("GIT_REMOTE_URL")
    if not remote_url:
        raise RuntimeError(
            f"{DATA_ROOT} has no .git and GIT_REMOTE_URL is not set -- "
            "cannot bootstrap the vault git working tree"
        )

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    is_empty = not any(DATA_ROOT.iterdir())
    if is_empty:
        subprocess.run(["git", "clone", remote_url, str(DATA_ROOT)], check=True)
    else:
        # disk has raw/state.db from a prior run but no .git (e.g. repo was
        # created after the disk already had data) -- init in place and wire
        # up the remote rather than clobbering existing files with a clone.
        subprocess.run(["git", "init", str(DATA_ROOT)], check=True)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=DATA_ROOT, check=True)
        subprocess.run(["git", "fetch", "origin"], cwd=DATA_ROOT, check=True)
        subprocess.run(["git", "checkout", "-B", "main", "origin/main"], cwd=DATA_ROOT, check=True)
