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


def push(repo_root, remote="origin", branch="main"):
    subprocess.run(["git", "push", remote, branch], cwd=repo_root, check=True)
