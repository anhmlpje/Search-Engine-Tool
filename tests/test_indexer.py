"""Tests for src.indexer and the data classes in src.models."""

from src.crawler import Page
from src.indexer import build_index, extract_fields
from src.models import (
    SCHEMA_VERSION,
    Document,
    FieldData,
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


# --- extract_fields ---------------------------------------------------------


class TestExtractFields:
    def test_quote_page_splits_into_three_fields(self) -> None:
        fields = extract_fields(QUOTE_PAGE_HTML)
        # text gets quote text only
        assert "world is good" in fields["text"]
        assert "Good friends are good" in fields["text"]
        # author gets author names only
        assert "Albert Einstein" in fields["author"]
        assert "Mark Twain" in fields["author"]
        # tag gets tag link text
        assert "world" in fields["tag"]
        assert "good" in fields["tag"]
        assert "friends" in fields["tag"]

    def test_each_field_excludes_others_content(self) -> None:
        fields = extract_fields(QUOTE_PAGE_HTML)
        # author names should not leak into text or tag
        assert "Albert" not in fields["text"]
        assert "Albert" not in fields["tag"]
        assert "Twain" not in fields["text"]
        # tag words should not appear in author
        # (author-only content is just the names)
        for chrome in ("Login", "Top", "footer", "copyright"):
            for value in fields.values():
                assert chrome not in value

    def test_author_page_populates_author_and_text(self) -> None:
        fields = extract_fields(AUTHOR_PAGE_HTML)
        assert "Albert Einstein" in fields["author"]
        assert "theoretical physicist" in fields["text"]
        # No quotes -> tag is empty
        assert fields["tag"].strip() == ""

    def test_empty_page_yields_empty_fields(self) -> None:
        fields = extract_fields(EMPTY_PAGE_HTML)
        for value in fields.values():
            assert value.strip() == ""


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

    def test_records_text_field_term_positions(self) -> None:
        """In QUOTE_PAGE_HTML the text field tokenises (in extraction order
        of quote 1 text + quote 2 text) to:

            0  the
            1  world
            2  is
            3  good
            4  good
            5  friends
            6  are
            7  good

        So 'good' in the text field has freq=3 at positions [3, 4, 7].
        """
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        text_posting = index.index["text"]["good"]["doc_001"]
        assert text_posting.freq == 3
        assert text_posting.positions == [3, 4, 7]

    def test_records_tag_field_term_positions(self) -> None:
        """The tag field tokenises to ['world', 'good', 'friends'] in
        extraction order. 'good' has freq=1 at position 1.
        """
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        tag_posting = index.index["tag"]["good"]["doc_001"]
        assert tag_posting.freq == 1
        assert tag_posting.positions == [1]

    def test_term_only_in_one_field_absent_from_others(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        # 'einstein' appears only in the author field
        assert "einstein" in index.index["author"]
        assert "einstein" not in index.index["text"]
        assert "einstein" not in index.index["tag"]

    def test_freq_equals_positions_length_invariant(self) -> None:
        """Across every (field, term, doc) triple, freq must equal len(positions)."""
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        for field_index in index.index.values():
            for postings in field_index.values():
                for posting in postings.values():
                    assert posting.freq == len(posting.positions)
                    assert posting.positions == sorted(posting.positions)

    def test_lowercases_terms(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        # 'Albert' appears uppercase in the HTML but is indexed lowercase
        assert "albert" in index.index["author"]
        assert "Albert" not in index.index["author"]

    def test_document_length_matches_field_total(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        doc = index.documents["doc_001"]
        assert doc.length == sum(fd.length for fd in doc.fields.values())

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
        # unique_terms is the union across fields
        union = set()
        for field_index in index.index.values():
            union.update(field_index.keys())
        assert index.metadata.unique_terms == len(union)
        assert index.metadata.total_tokens == sum(
            doc.length for doc in index.documents.values()
        )
        assert index.metadata.politeness_delay_seconds == 6.0

    def test_empty_pages_produce_zero_length_documents(self) -> None:
        pages = [_page("https://site.test/empty", EMPTY_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        doc = index.documents["doc_001"]
        assert doc.length == 0
        assert all(fd.length == 0 for fd in doc.fields.values())
        assert index.metadata.total_tokens == 0
        for field_index in index.index.values():
            assert field_index == {}

    def test_idempotent(self) -> None:
        pages_a = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        pages_b = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        a = build_index(pages_a, base_url="https://site.test/")
        b = build_index(pages_b, base_url="https://site.test/")
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

    def test_document_stores_field_tokens_for_snippets(self) -> None:
        pages = [_page("https://site.test/", QUOTE_PAGE_HTML)]
        index = build_index(pages, base_url="https://site.test/")
        text_field = index.documents["doc_001"].fields["text"]
        # Tokens preserved in extraction order, lowercased, no punctuation
        assert text_field.tokens[:4] == ["the", "world", "is", "good"]
        assert text_field.length == len(text_field.tokens)


# --- Models: round-trip ----------------------------------------------------


class TestModelsRoundTrip:
    def test_field_data_round_trip(self) -> None:
        fd = FieldData(length=3, tokens=["a", "b", "c"])
        assert FieldData.from_dict(fd.to_dict()) == fd

    def test_document_round_trip(self) -> None:
        d = Document(
            url="https://x/",
            title="X",
            length=5,
            fields={
                "text": FieldData(length=3, tokens=["a", "b", "c"]),
                "author": FieldData(length=2, tokens=["x", "y"]),
                "tag": FieldData(length=0, tokens=[]),
            },
        )
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
            documents={
                "doc_001": Document(
                    url="https://x/",
                    title="X",
                    length=2,
                    fields={
                        "text": FieldData(length=2, tokens=["hello", "world"]),
                        "author": FieldData(length=0, tokens=[]),
                        "tag": FieldData(length=0, tokens=[]),
                    },
                )
            },
            index={
                "text": {
                    "hello": {"doc_001": Posting(freq=1, positions=[0])},
                    "world": {"doc_001": Posting(freq=1, positions=[1])},
                },
                "author": {},
                "tag": {},
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
            index={"text": {}, "author": {}, "tag": {}},
        )
        assert index.to_dict()["schema_version"] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 2
