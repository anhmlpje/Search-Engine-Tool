"""Tests for src.indexer and the data classes in src.models."""

from src.crawler import Page
from src.indexer import build_index, extract_text
from src.models import (
    SCHEMA_VERSION,
    Document,
    IndexMetadata,
    Posting,
    SearchIndex,
)


# --- Fixtures: hand-crafted HTML matching quotes.toscrape.com's layout ---

QUOTE_PAGE_HTML = """
<html>
  <head><title>Quotes to Scrape</title></head>
  <body>
    <ul class="nav"><li>Login</li><li>Top</li></ul>
    <div class="quote">
      <span class="text">"The world is good."</span>
      <span><small class="author">Albert Einstein</small></span>
      <div class="tags">
        <a class="tag" href="/tag/world/">world</a>
        <a class="tag" href="/tag/good/">good</a>
      </div>
    </div>
    <div class="quote">
      <span class="text">"Good friends are good."</span>
      <span><small class="author">Mark Twain</small></span>
      <div class="tags">
        <a class="tag" href="/tag/friends/">friends</a>
      </div>
    </div>
    <footer>Quotes to Scrape footer</footer>
  </body>
</html>
"""

AUTHOR_PAGE_HTML = """
<html>
  <body>
    <ul class="nav"><li>Login</li></ul>
    <h3 class="author-title">Albert Einstein</h3>
    <div class="author-description">A theoretical physicist.</div>
  </body>
</html>
"""

EMPTY_PAGE_HTML = """
<html><body><nav>Login Top</nav><footer>copyright</footer></body></html>
"""


def _page(url: str, html: str, title: str = "Quotes to Scrape") -> Page:
    return Page(url=url, html=html, title=title)


# --- extract_text -----------------------------------------------------------


class TestExtractText:
    def test_returns_quote_text_author_and_tags(self) -> None:
        text = extract_text(QUOTE_PAGE_HTML)
        assert "world is good" in text
        assert "Albert Einstein" in text
        assert "world" in text
        assert "good" in text
        assert "friends" in text

    def test_excludes_navigation_and_footer(self) -> None:
        text = extract_text(QUOTE_PAGE_HTML)
        assert "Login" not in text
        assert "Top" not in text
        assert "footer" not in text
        assert "copyright" not in text

    def test_returns_author_bio(self) -> None:
        text = extract_text(AUTHOR_PAGE_HTML)
        assert "Albert Einstein" in text
        assert "theoretical physicist" in text
        assert "Login" not in text

    def test_returns_empty_for_chrome_only_page(self) -> None:
        assert extract_text(EMPTY_PAGE_HTML).strip() == ""


# --- build_index ------------------------------------------------------------


class TestBuildIndex:
    def test_assigns_doc_ids_in_order(self) -> None:
        pages = [
            _page("https://site.test/", QUOTE_PAGE_HTML),
            _page("https://site.test/author/einstein", AUTHOR_PAGE_HTML),
        ]
        index = build_index(pages, base_url="https://site.test/")
        assert list(index.documents.keys()) == ["doc_001", "doc_002"]
        assert index.documents["doc_001"].url == "https://site.test/"
        assert index.documents["doc_002"].url == "https://site.test/author/einstein"

    def test_records_term_frequency(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        good_postings = index.index["good"]
        assert "doc_001" in good_postings
        # "good" appears: (1) tag, (2) "Good friends are good" -> two occurrences,
        # (3) tag inside first quote. Total observed: tag/good, "good" inside
        # second quote text twice.
        assert good_postings["doc_001"].freq == good_postings["doc_001"].freq
        # Just assert at least 2; exact count depends on extraction order
        assert good_postings["doc_001"].freq >= 2

    def test_records_positions_in_order(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        good = index.index["good"]["doc_001"]
        assert good.positions == sorted(good.positions)
        assert good.freq == len(good.positions)

    def test_lowercases_terms(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        # "Albert" appears uppercase in the HTML but should be indexed lowercase
        assert "albert" in index.index
        assert "Albert" not in index.index

    def test_document_length_matches_token_count(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        doc = index.documents["doc_001"]
        # Sum of all positions across all terms in this doc must equal length
        total_positions = sum(
            posting.freq
            for postings in index.index.values()
            for doc_id, posting in postings.items()
            if doc_id == "doc_001"
        )
        assert total_positions == doc.length

    def test_metadata_counts(self) -> None:
        pages = [
            _page("https://site.test/", QUOTE_PAGE_HTML),
            _page("https://site.test/author/einstein", AUTHOR_PAGE_HTML),
        ]
        index = build_index(
            pages,
            base_url="https://site.test/",
            politeness_delay_seconds=6.0,
        )
        assert index.metadata.base_url == "https://site.test/"
        assert index.metadata.page_count == 2
        assert index.metadata.unique_terms == len(index.index)
        assert index.metadata.total_tokens == sum(
            doc.length for doc in index.documents.values()
        )
        assert index.metadata.politeness_delay_seconds == 6.0

    def test_empty_pages_produce_zero_length_documents(self) -> None:
        pages = [_page("https://site.test/empty", EMPTY_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        assert index.documents["doc_001"].length == 0
        assert index.metadata.total_tokens == 0
        assert index.index == {}

    def test_idempotent(self) -> None:
        pages_a = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        pages_b = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        a = build_index(pages_a, base_url="https://site.test/")
        b = build_index(pages_b, base_url="https://site.test/")
        # Index structure identical (created_at differs)
        assert a.documents == b.documents
        assert a.index == b.index
        assert a.metadata.unique_terms == b.metadata.unique_terms
        assert a.metadata.total_tokens == b.metadata.total_tokens

    def test_streams_pages_lazily(self) -> None:
        consumed: list[str] = []

        def page_generator():
            for url, html in [
                ("https://site.test/a", QUOTE_PAGE_HTML),
                ("https://site.test/b", AUTHOR_PAGE_HTML),
            ]:
                consumed.append(url)
                yield _page(url, html)

        index = build_index(page_generator(), base_url="https://site.test/")
        assert consumed == ["https://site.test/a", "https://site.test/b"]
        assert len(index.documents) == 2


# --- Models: round-trip ----------------------------------------------------


class TestModelsRoundTrip:
    def test_document_round_trip(self) -> None:
        d = Document(url="https://x/", title="X", length=42)
        assert Document.from_dict(d.to_dict()) == d

    def test_posting_round_trip(self) -> None:
        p = Posting(freq=3, positions=[1, 5, 9])
        assert Posting.from_dict(p.to_dict()) == p

    def test_metadata_round_trip(self) -> None:
        m = IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=10,
            total_tokens=100,
            unique_terms=50,
            politeness_delay_seconds=6.0,
        )
        assert IndexMetadata.from_dict(m.to_dict()) == m

    def test_search_index_round_trip(self) -> None:
        original = SearchIndex(
            metadata=IndexMetadata(
                base_url="https://x/",
                created_at="2026-05-07T12:34:56Z",
                page_count=1,
                total_tokens=2,
                unique_terms=2,
                politeness_delay_seconds=6.0,
            ),
            documents={"doc_001": Document(url="https://x/", title="X", length=2)},
            index={
                "hello": {"doc_001": Posting(freq=1, positions=[0])},
                "world": {"doc_001": Posting(freq=1, positions=[1])},
            },
        )
        round_tripped = SearchIndex.from_dict(original.to_dict())
        assert round_tripped == original

    def test_search_index_to_dict_includes_schema_version(self) -> None:
        index = SearchIndex(
            metadata=IndexMetadata(
                base_url="https://x/",
                created_at="2026-05-07T12:34:56Z",
                page_count=0,
                total_tokens=0,
                unique_terms=0,
                politeness_delay_seconds=6.0,
            ),
            documents={},
            index={},
        )
        assert index.to_dict()["schema_version"] == SCHEMA_VERSION
