"""Tokenisation, HTTP helper, and clock injection."""

import re
import time
from typing import Protocol

import requests


_TOKEN_RE = re.compile(r"\b\w+\b")


def tokenize(text: str) -> list[str]:
    r"""Lowercase the input and extract word tokens.

    Uses Python 3's Unicode-aware ``\w``, so non-ASCII letters survive while
    punctuation -- including curly apostrophes -- splits words at the
    boundary.
    """
    return _TOKEN_RE.findall(text.lower())


class Clock(Protocol):
    """Minimal sleep abstraction so tests can replace real sleeping."""

    def sleep(self, seconds: float) -> None: ...


class RealClock:
    """Production clock backed by :func:`time.sleep`."""

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class HttpError(Exception):
    """Raised when a URL cannot be retrieved after all retry attempts."""


def safe_request(
    url: str,
    *,
    timeout: float = 10.0,
    retries: int = 2,
    session: requests.Session | None = None,
    clock: Clock | None = None,
    retry_delay: float = 0.0,
) -> requests.Response:
    """GET ``url`` with up to ``retries`` extra attempts on transient errors.

    Retries are themselves requests to the website, so the brief's
    politeness window applies between them just as it does between
    successful requests. When the caller provides a ``clock`` and a
    positive ``retry_delay``, the helper sleeps for ``retry_delay`` before
    each retry attempt -- the crawler always does this so the 6-second
    window is honoured even when a fetch fails. With no clock supplied the
    helper retries immediately, which is convenient for unit tests that
    only care about HTTP behaviour.
    """
    sess = session if session is not None else requests
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if attempt > 0 and clock is not None and retry_delay > 0:
            clock.sleep(retry_delay)
        try:
            response = sess.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
    raise HttpError(f"failed to fetch {url}: {last_error}")
