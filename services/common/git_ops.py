"""Thin wrapper around git commits for the vault working tree. Shared by
ingestion (commits raw/) and wiki_writer (commits vault/) -- commit history
doubles as the audit trail for both.
"""
import subprocess


def commit(repo_root, message, paths=None):
    if paths:
        subprocess.run(["git", "add", *paths], cwd=repo_root, check=True)
    else:
        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)

    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repo_root
    )
    if result.returncode == 0:
        return False  # nothing staged, nothing to commit

    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    return True


class PushConflictError(Exception):
    """Raised when the remote has diverged and rebasing local commits onto it
    fails -- i.e. an actual conflict, not just "remote moved forward" (which
    push() already resolves automatically via fetch+rebase). This needs a
    human to look at the working tree; never resolved automatically."""


def push(repo_root, remote="origin", branch="main"):
    """Push local commits, first integrating any remote-side commits this
    working tree doesn't have yet (SPEC.md's git_pushed_at retry logic and
    manual testing/debugging both write commits to the same GitHub repo, so
    a plain non-fast-forward push is an expected, recoverable case here --
    not just a rare race).
    """
    subprocess.run(["git", "fetch", remote, branch], cwd=repo_root, check=True)

    result = subprocess.run(
        ["git", "rebase", f"{remote}/{branch}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=repo_root)
        raise PushConflictError(
            f"rebase onto {remote}/{branch} failed, working tree left as before "
            f"the attempt: {result.stderr}"
        )

    subprocess.run(["git", "push", remote, branch], cwd=repo_root, check=True)
