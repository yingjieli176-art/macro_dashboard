"""Bounded, single-flight refreshes for dated last-good observations."""
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time


class BackgroundRefresh:
    def __init__(self, max_workers=3, retry_seconds=60):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="source-refresh")
        self._lock = threading.Lock()
        self._pending = set()
        self._attempted = {}
        self._retry_seconds = retry_seconds

    def submit(self, key, refresh):
        with self._lock:
            now = time.monotonic()
            if key in self._pending or now - self._attempted.get(key, -float("inf")) < self._retry_seconds:
                return False
            self._pending.add(key)
            self._attempted[key] = now
        try:
            self._pool.submit(self._run, key, refresh)
        except RuntimeError:
            with self._lock:
                self._pending.discard(key)
            return False
        return True

    def _run(self, key, refresh):
        try:
            refresh()
        except Exception:
            logging.exception("Background source refresh failed: %s", key)
        finally:
            with self._lock:
                self._pending.discard(key)

