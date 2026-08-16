"""Bounded-batch helper shared by ingestion and wiki_writer.

Per SPEC.md #7: each run processes up to N items or M minutes, whichever
comes first, then the caller checkpoints in state.db and exits. A large
backlog spreads itself across multiple scheduled runs automatically.
"""
import time


class BatchLimiter:
    def __init__(self, max_items, max_seconds):
        self.max_items = max_items
        self.max_seconds = max_seconds
        self.count = 0
        self._start = time.monotonic()

    def should_continue(self):
        if self.count >= self.max_items:
            return False
        if (time.monotonic() - self._start) >= self.max_seconds:
            return False
        return True

    def record(self):
        self.count += 1
