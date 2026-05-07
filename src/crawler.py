"""Polite breadth-first crawler with injectable clock."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.utils import Clock, HttpError, RealClock, safe_request


@dataclass(frozen=True)
class Page:
    """A successfully fetched page."""

    url: str
    html: str
    title: str


class Crawler:
    """BFS crawler restricted to the start URL's host.

    Yields :class:`Page` records lazily so the indexer can stream rather
    than buffer the entire site. The constructor takes a :class:`Clock`
    and a ``delay_seconds`` so tests can verify politeness without
    actually sleeping.
    """

    def __init__(
        self,
        start_url: str,
        *,
        delay_seconds: float = 6.0,
        clock: Clock | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.start_url = start_url
        self.delay_seconds = delay_seconds
        self.clock: Clock = clock if clock is not None else RealClock()
        self.session = session

    def crawl(self) -> Iterator[Page]:
        """Walk the site in breadth-first order, yielding each fetched page."""
        host = urlparse(self.start_url).netloc
        seen: set[str] = {self.start_url}
        frontier: deque[str] = deque([self.start_url])
        first = True

        while frontier:
            url = frontier.popleft()

            if not first:
                self.clock.sleep(self.delay_seconds)
            first = False

            try:
                response = safe_request(url, session=self.session)
            except HttpError:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            title_tag = soup.title
            title = (title_tag.string or "").strip() if title_tag is not None else ""

            yield Page(url=url, html=response.text, title=title)

            for link in soup.find_all("a", href=True):
                absolute = urljoin(url, link["href"])
                absolute, _ = urldefrag(absolute)
                if urlparse(absolute).netloc == host and absolute not in seen:
                    seen.add(absolute)
                    frontier.append(absolute)
