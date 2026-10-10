"""CI-only process-wide offline transport, safe across concurrent app sessions.

Never import this module from the production app. The standalone acceptance
server exits after the test; hooks deliberately stay installed until then.
"""
import threading
import urllib.request

import requests

_lock = threading.Lock()
_installed = False


def _offline_http(*args, **kwargs):
    raise requests.Timeout("offline browser acceptance")


def _offline_urlopen(*args, **kwargs):
    raise OSError("offline browser acceptance")


def install():
    global _installed
    with _lock:
        if not _installed:
            requests.sessions.Session.request = _offline_http
            urllib.request.urlopen = _offline_urlopen
            _installed = True
