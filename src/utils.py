"""Tokenisation, HTTP helper, and clock injection."""

from __future__ import annotations

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
) -> requests.Response:
    """GET ``url`` with up to ``retries`` extra attempts on transient errors.

    The crawler is responsible for the politeness window between successful
    requests; this helper only retries on failure and raises
    :class:`HttpError` if all attempts fail.
    """
    sess = session if session is not None else requests
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            response = sess.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
    raise HttpError(f"failed to fetch {url}: {last_error}")
