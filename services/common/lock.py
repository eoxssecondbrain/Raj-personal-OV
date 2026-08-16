"""Concurrency guard for ingestion + wiki_writer cron jobs.

Two-layer protection per SPEC.md #7:
  1. Bounded batches (enforced by callers, not here) keep individual runs short.
  2. This lock is the backstop against overlapping runs when a batch runs
     longer than expected or a run crashes mid-way.
"""
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

STALE_MULTIPLIER = 2  # lock older than STALE_MULTIPLIER * expected_runtime_seconds is treated as crashed


class LockHeldError(Exception):
    """Raised when another run currently holds the lock and it isn't stale."""


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    return datetime.fromisoformat(ts)


def try_acquire(conn, job_name, expected_runtime_seconds):
    """Attempt to acquire the named lock. Raises LockHeldError if held and not stale.

    Clears and takes over a stale lock (older than STALE_MULTIPLIER * expected_runtime_seconds).
    """
    row = conn.execute(
        "SELECT acquired_at, pid FROM locks WHERE job_name = ?", (job_name,)
    ).fetchone()

    if row is not None:
        acquired_at = _parse(row["acquired_at"])
        age = (_now() - acquired_at).total_seconds()
        threshold = STALE_MULTIPLIER * expected_runtime_seconds
        if age < threshold:
            raise LockHeldError(
                f"lock '{job_name}' held since {row['acquired_at']} "
                f"(age={age:.0f}s, threshold={threshold:.0f}s) by pid={row['pid']}"
            )
        # stale: crashed run, clear and take over
        conn.execute("DELETE FROM locks WHERE job_name = ?", (job_name,))

    conn.execute(
        "INSERT INTO locks (job_name, acquired_at, pid) VALUES (?, ?, ?)",
        (job_name, _now().isoformat(), os.getpid()),
    )
    conn.commit()


def release(conn, job_name):
    conn.execute("DELETE FROM locks WHERE job_name = ?", (job_name,))
    conn.commit()


@contextmanager
def job_lock(conn, job_name, expected_runtime_seconds):
    """Usage:

        with job_lock(conn, "ingestion", expected_runtime_seconds=600):
            ... do bounded-batch work ...

    Guarantees release on success, exception, or platform kill signal handled
    upstream (try/finally covers normal exceptions; a hard SIGKILL still leaves
    a lock row, which is exactly what the staleness check above recovers from).
    """
    try_acquire(conn, job_name, expected_runtime_seconds)
    try:
        yield
    finally:
        release(conn, job_name)
