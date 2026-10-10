"""Process-wide bounded workers and request budgets; no Streamlit UI in workers."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from functools import wraps
from pathlib import Path
import threading
import time

import requests
import streamlit as st

_DEADLINE = ContextVar("macro_request_deadline", default=None)
_HTTP_SLOTS = threading.BoundedSemaphore(8)
_SOURCE_LOCK = threading.RLock()
_SOURCE_FAILURES = {}
_SOURCE_LAST_GOOD = {}


class _UnavailableSource(Exception):
    def __init__(self, frame):
        self.frame = frame


def observed_cache(paths=None, ttl=3600):
    """Cache observed frames by snapshot revision; retry empty results after 10s."""
    def decorate(function):
        source_file = Path(function.__code__.co_filename)
        try:
            code_revision = source_file.stat().st_mtime_ns
        except OSError:
            code_revision = 0
        identity = (function.__module__, function.__qualname__, code_revision)

        @st.cache_data(ttl=ttl, max_entries=64, show_spinner=False)
        def cached(source_identity, revision, args, kwargs):
            frame = function(*args, **kwargs)
            if getattr(frame, "empty", False):
                raise _UnavailableSource(frame)
            return frame

        @wraps(function)
        def read(*args, **kwargs):
            revision = []
            for path in paths() if paths else ():
                try:
                    stat = path.stat()
                    revision.append((str(path), stat.st_mtime_ns, stat.st_size))
                except OSError:
                    revision.append((str(path), None, None))
            revision = tuple(revision)
            key = (identity, revision, args, tuple(sorted(kwargs.items())))
            good_key = (identity, args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with _SOURCE_LOCK:
                failed = _SOURCE_FAILURES.get(key)
                if failed and now-failed[0] < 10:
                    return failed[1].copy()
            try:
                frame = cached(identity, revision, args, kwargs)
                with _SOURCE_LOCK:
                    _SOURCE_FAILURES.pop(key, None)
                    _SOURCE_LAST_GOOD[good_key] = frame.copy()
                    if len(_SOURCE_LAST_GOOD) > 64:
                        _SOURCE_LAST_GOOD.pop(next(iter(_SOURCE_LAST_GOOD)))
                return frame
            except _UnavailableSource as failure:
                frame = failure.frame
                with _SOURCE_LOCK:
                    previous = _SOURCE_LAST_GOOD.get(good_key)
                    if previous is not None:
                        frame = previous.copy()
                        frame.attrs.update({"is_stale": True, "is_fallback": True})
                    _SOURCE_FAILURES[key] = (now, frame.copy())
                    if len(_SOURCE_FAILURES) > 64:
                        _SOURCE_FAILURES.pop(next(iter(_SOURCE_FAILURES)))
                return frame

        def clear():
            cached.clear()
            with _SOURCE_LOCK:
                for storage in (_SOURCE_FAILURES, _SOURCE_LAST_GOOD):
                    for key in list(storage):
                        if key[0] == identity:
                            storage.pop(key, None)
        read.clear = clear
        return read
    return decorate


@contextmanager
def request_budget(seconds):
    previous = _DEADLINE.get()
    deadline = time.monotonic() + seconds
    token = _DEADLINE.set(min(previous, deadline) if previous is not None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def http_get(url, **kwargs):
    """Bound retries cumulatively and cap concurrent public-source requests."""
    deadline = _DEADLINE.get()
    remaining = max(0, deadline - time.monotonic()) if deadline is not None else 12.0
    if remaining <= 0 or not _HTTP_SLOTS.acquire(timeout=remaining):
        raise requests.Timeout("Source request budget exhausted")
    try:
        remaining = max(0, deadline - time.monotonic()) if deadline is not None else 12.0
        if remaining <= 0:
            raise requests.Timeout("Source request budget exhausted")
        original = kwargs.get("timeout", (3.0, 8.0))
        if isinstance(original, tuple):
            kwargs["timeout"] = tuple(min(float(value), remaining) for value in original)
        else:
            kwargs["timeout"] = min(float(original), remaining)
        return requests.get(url, **kwargs)
    finally:
        _HTTP_SLOTS.release()


class WorkerPool:
    """Coalesce in-flight work and bound the queue across concurrent sessions."""
    def __init__(self, workers, name, max_pending=128):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self._lock = threading.RLock()
        self._pending = {}
        self._max_pending = max_pending
        self._closed = False

    def submit(self, key, job, budget=8.0):
        with self._lock:
            if self._closed:
                raise RuntimeError("Worker pool closed")
            previous = self._pending.get(key)
            if previous is not None and not previous.done():
                return previous
            if len(self._pending) >= self._max_pending:
                raise RuntimeError("Worker queue full")
            context = copy_context()
            def run():
                with request_budget(budget):
                    return job()
            future = self._pool.submit(context.run, run)
            self._pending[key] = future
            def finished(_):
                with self._lock:
                    if self._pending.get(key) is future:
                        self._pending.pop(key, None)
            future.add_done_callback(finished)
            return future

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)


@st.cache_resource(show_spinner=False, on_release=lambda pool: pool.close())
def worker_pool(name, workers=6):
    return WorkerPool(workers, name)


def submit_jobs(jobs, name="macro-chart", workers=6, budget=8.0, revision=None):
    pool = worker_pool(name, workers)
    futures = {}
    for key, job in jobs.items():
        try:
            future = pool.submit((key, revision), job, budget)
        except RuntimeError:
            continue
        futures[future] = key
    return futures


def completed_jobs(futures, budget=8.0):
    """Yield completed work without waiting for running tasks after the budget."""
    pending = set(futures)
    deadline = time.monotonic() + budget
    while pending:
        done, pending = wait(pending, timeout=max(0, deadline-time.monotonic()), return_when=FIRST_COMPLETED)
        if not done:
            break
        for future in done:
            yield futures[future], future


class PeriodicWorker:
    def __init__(self, job, interval, name):
        self._stop = threading.Event()
        def run():
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    with request_budget(12):
                        job()
                except Exception:
                    import logging
                    logging.exception("Periodic source update failed: %s", name)
                self._stop.wait(max(1, interval-(time.monotonic()-started)))
        self.thread = threading.Thread(target=run, name=name, daemon=True)
        self.thread.start()

    def close(self):
        self._stop.set()
        self.thread.join(timeout=.1)
