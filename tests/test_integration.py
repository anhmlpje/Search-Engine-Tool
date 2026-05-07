"""End-to-end integration tests wiring crawler -> indexer -> storage -> search.

Two perspectives are covered:

1. ``TestPipeline`` exercises the function-level chain directly: a mocked
   two-page site is crawled, the resulting iterable is indexed, the index
   is round-tripped through JSON, and queries are run against the loaded
   copy.
2. ``TestShellSession`` drives the same flow through ``SearchShell`` so
   that the CLI parsing, command dispatch, and output formatting are
   exercised as a single cohesive session rather than command-by-command.
"""

import io
from pathlib import Path

import responses

from src.crawler import Crawler
from src.indexer import build_index
from src.main import SearchShell
from src.search import find, find_phrase, print_word
from src.storage import load, save


PAGE_HOME = """
<html>
  <head><title>Quotes - Home</title></head>
  <body>
    <ul class="nav"><li>Login</li></ul>
    <div class="quote">
      <span class="text">"Good friends are good."</span>
      <span><small class="author">Mark Twain</small></span>
      <div class="tags">
        <a class="tag" href="/tag/friends/">friends</a>
        <a class="tag" href="/tag/good/">good</a>
      </div>
    </div>
    <a href="/page/2/">next</a>
    <footer>copyright</footer>
  </body>
</html>
"""

PAGE_2 = """
<html>
  <head><title>Quotes - Page 2</title></head>
  <body>
    <div class="quote">
      <span class="text">"The opposite of love is indifference."</span>
      <span><small class="author">Eli Wiesel</small></span>
      <div class="tags">
        <a class="tag" href="/tag/indifference/">indifference</a>
      </div>
    </div>
  </body>
</html>
"""


class FakeClock:
    """A clock that records sleep durations without sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


def _register_two_page_site() -> None:
    """Mock the two pages we link, leaving tag URLs unmocked so the
    crawler exercises its retry-then-skip path on dead links too."""
    responses.add(
        responses.GET, "https://site.test/", body=PAGE_HOME, status=200
    )
    responses.add(
        responses.GET, "https://site.test/page/2/", body=PAGE_2, status=200
    )


class TestPipeline:
    @responses.activate
    def test_full_pipeline_end_to_end(self, tmp_path: Path) -> None:
        _register_two_page_site()
        index_path = tmp_path / "idx.json"

        crawler = Crawler(
            "https://site.test/", delay_seconds=0.0, clock=FakeClock()
        )
        index = build_index(
            crawler.crawl(),
            base_url="https://site.test/",
            politeness_delay_seconds=6.0,
        )

        # Round-trip through disk
        save(index, index_path)
        loaded = load(index_path)
        assert loaded == index

        # Single-word inspection
        view = print_word(loaded, "indifference")
        assert "doc_" in view
        assert "https://site.test/page/2/" in view

        # AND query: "good friends" appears in the home page
        and_results = find(loaded, ["good", "friends"])
        assert len(and_results) >= 1
        assert any(r.url == "https://site.test/" for r in and_results)

        # Phrase query: "good friends" appears adjacent in the home page text
        phrase_results = find_phrase(loaded, "good friends")
        assert len(phrase_results) == 1
        assert phrase_results[0].url == "https://site.test/"
        assert phrase_results[0].score == 1.0

    @responses.activate
    def test_corpus_metadata_reflects_crawl(self, tmp_path: Path) -> None:
        _register_two_page_site()
        crawler = Crawler(
            "https://site.test/", delay_seconds=0.0, clock=FakeClock()
        )
        index = build_index(
            crawler.crawl(),
            base_url="https://site.test/",
            politeness_delay_seconds=6.0,
        )
        meta = index.metadata
        assert meta.base_url == "https://site.test/"
        assert meta.page_count >= 2  # home + /page/2/, possibly skipped tags
        union = set()
        for field_index in index.index.values():
            union.update(field_index.keys())
        assert meta.unique_terms == len(union)
        assert meta.total_tokens == sum(d.length for d in index.documents.values())


class TestShellSession:
    @responses.activate
    def test_build_load_print_find_session(self, tmp_path: Path) -> None:
        """Drive the four primary commands through a single SearchShell
        session and assert each step left a recognisable trace in stdout."""
        _register_two_page_site()
        index_path = tmp_path / "idx.json"

        shell = SearchShell(
            base_url="https://site.test/",
            index_path=index_path,
            delay_seconds=0.0,
        )
        shell.stdin = io.StringIO(
            "build\n"
            "load\n"
            "print indifference\n"
            "find good friends\n"
            'find "good friends"\n'
            "stats\n"
            "exit\n"
        )
        shell.stdout = io.StringIO()
        shell.use_rawinput = False
        shell.cmdloop(intro="")
        out = shell.stdout.getvalue()

        # Build summary must appear and the file must exist
        assert "[built]" in out
        assert "[saved]" in out
        assert index_path.exists()

        # Load summary
        assert "[loaded]" in out

        # Print indifference reaches the right page
        assert "https://site.test/page/2/" in out

        # AND find: home page contains both terms
        assert "https://site.test/" in out

        # Phrase find: home page has the adjacent pair
        assert "occurrences=" in out

        # stats prints summary + top-token table
        assert "[stats]" in out
        assert "top 20 tokens" in out

    @responses.activate
    def test_session_handles_unknown_word_gracefully(
        self, tmp_path: Path
    ) -> None:
        _register_two_page_site()
        shell = SearchShell(
            base_url="https://site.test/",
            index_path=tmp_path / "idx.json",
            delay_seconds=0.0,
        )
        shell.stdin = io.StringIO(
            "build\n"
            "find xyz_definitely_not_in_corpus\n"
            "exit\n"
        )
        shell.stdout = io.StringIO()
        shell.use_rawinput = False
        shell.cmdloop(intro="")
        out = shell.stdout.getvalue()
        assert "no matches" in out
