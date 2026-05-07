"""Tests for src.crawler."""

import responses

from src.crawler import Crawler


class FakeClock:
    """Records sleep durations without actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


PAGE_HOME = """
<html><head><title>Home</title></head>
<body>
  <a href="/page2">P2</a>
  <a href="https://other.example/elsewhere">off-host</a>
</body></html>
"""

PAGE_2 = """
<html><head><title>Page 2</title></head>
<body>
  <a href="/page3">P3</a>
  <a href="/page2">self-link</a>
  <a href="/">home</a>
  <a href="/page2#section">fragment</a>
</body></html>
"""

PAGE_3 = """
<html><head><title>Page 3</title></head>
<body>End of the road.</body></html>
"""


def _register_three_page_site() -> None:
    responses.add(responses.GET, "https://site.test/", body=PAGE_HOME, status=200)
    responses.add(responses.GET, "https://site.test/page2", body=PAGE_2, status=200)
    responses.add(responses.GET, "https://site.test/page3", body=PAGE_3, status=200)


class TestCrawler:
    @responses.activate
    def test_discovers_all_in_host_pages(self) -> None:
        _register_three_page_site()
        crawler = Crawler("https://site.test/", clock=FakeClock())
        urls = {page.url for page in crawler.crawl()}
        assert urls == {
            "https://site.test/",
            "https://site.test/page2",
            "https://site.test/page3",
        }

    @responses.activate
    def test_sleeps_between_requests_only(self) -> None:
        _register_three_page_site()
        clock = FakeClock()
        crawler = Crawler("https://site.test/", delay_seconds=6.0, clock=clock)
        list(crawler.crawl())
        # Three pages -> two sleeps; the first request is not preceded by a sleep.
        assert clock.calls == [6.0, 6.0]

    @responses.activate
    def test_respects_configured_delay(self) -> None:
        _register_three_page_site()
        clock = FakeClock()
        crawler = Crawler("https://site.test/", delay_seconds=2.5, clock=clock)
        list(crawler.crawl())
        assert clock.calls == [2.5, 2.5]

    @responses.activate
    def test_skips_off_host_links(self) -> None:
        _register_three_page_site()
        crawler = Crawler("https://site.test/", clock=FakeClock())
        urls = [page.url for page in crawler.crawl()]
        for url in urls:
            assert "other.example" not in url

    @responses.activate
    def test_dedupes_seen_urls(self) -> None:
        _register_three_page_site()
        crawler = Crawler("https://site.test/", clock=FakeClock())
        list(crawler.crawl())
        # Despite self-link, home-link, and a fragment variant on page2,
        # each URL is fetched exactly once.
        assert len(responses.calls) == 3

    @responses.activate
    def test_continues_past_failed_page(self) -> None:
        responses.add(responses.GET, "https://site.test/", body=PAGE_HOME, status=200)
        for _ in range(3):
            responses.add(responses.GET, "https://site.test/page2", status=500)
        crawler = Crawler("https://site.test/", clock=FakeClock())
        urls = [page.url for page in crawler.crawl()]
        assert "https://site.test/" in urls
        assert "https://site.test/page2" not in urls

    @responses.activate
    def test_yields_titles(self) -> None:
        _register_three_page_site()
        crawler = Crawler("https://site.test/", clock=FakeClock())
        titles = {page.title for page in crawler.crawl()}
        assert titles == {"Home", "Page 2", "Page 3"}

    @responses.activate
    def test_yields_page_html(self) -> None:
        _register_three_page_site()
        crawler = Crawler("https://site.test/", clock=FakeClock())
        pages = list(crawler.crawl())
        for page in pages:
            assert "<html>" in page.html.lower()

    @responses.activate
    def test_handles_missing_title_tag(self) -> None:
        responses.add(
            responses.GET,
            "https://site.test/",
            body="<html><body>no title here</body></html>",
            status=200,
        )
        crawler = Crawler("https://site.test/", clock=FakeClock())
        pages = list(crawler.crawl())
        assert len(pages) == 1
        assert pages[0].title == ""

    @responses.activate
    def test_dedupes_repeated_link_within_page(self) -> None:
        dupe_page = (
            '<html><body>'
            '<a href="/x">a</a><a href="/x">b</a><a href="/x#frag">c</a>'
            '</body></html>'
        )
        target_page = "<html><body>x</body></html>"
        responses.add(responses.GET, "https://site.test/", body=dupe_page, status=200)
        responses.add(responses.GET, "https://site.test/x", body=target_page, status=200)
        crawler = Crawler("https://site.test/", clock=FakeClock())
        list(crawler.crawl())
        # Three identical links to /x -> /x fetched exactly once.
        assert len(responses.calls) == 2
