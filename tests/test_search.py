"""Tests for src.search."""

from src.models import Document, IndexMetadata, Posting, SearchIndex
from src.search import find, print_word


def _two_doc_index() -> SearchIndex:
    return SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=2,
            total_tokens=4,
            unique_terms=3,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(url="https://x/a", title="A", length=2),
            "doc_002": Document(url="https://x/b", title="B", length=2),
        },
        index={
            "hello": {
                "doc_001": Posting(freq=1, positions=[0]),
                "doc_002": Posting(freq=1, positions=[0]),
            },
            "world": {
                "doc_001": Posting(freq=1, positions=[1]),
            },
            "friends": {
                "doc_002": Posting(freq=1, positions=[1]),
            },
        },
    )


class TestPrintWord:
    def test_word_present_lists_each_document(self) -> None:
        out = print_word(_two_doc_index(), "hello")
        assert "hello" in out
        assert "doc_001" in out
        assert "doc_002" in out
        assert "freq=1" in out
        assert "https://x/a" in out

    def test_word_absent_returns_no_matches(self) -> None:
        out = print_word(_two_doc_index(), "missing")
        assert "no matches" in out

    def test_case_insensitive_lookup(self) -> None:
        out = print_word(_two_doc_index(), "HELLO")
        assert "doc_001" in out

    def test_documents_sorted_by_doc_id(self) -> None:
        out = print_word(_two_doc_index(), "hello")
        idx_001 = out.index("doc_001")
        idx_002 = out.index("doc_002")
        assert idx_001 < idx_002


class TestFind:
    def test_single_term_returns_all_matching_docs(self) -> None:
        results = find(_two_doc_index(), ["hello"])
        assert {r.doc_id for r in results} == {"doc_001", "doc_002"}

    def test_multi_term_takes_intersection(self) -> None:
        results = find(_two_doc_index(), ["hello", "world"])
        assert len(results) == 1
        assert results[0].doc_id == "doc_001"

    def test_disjoint_terms_yield_empty(self) -> None:
        # world is in doc_001; friends in doc_002. AND -> nothing.
        assert find(_two_doc_index(), ["world", "friends"]) == []

    def test_unknown_term_yields_empty(self) -> None:
        assert find(_two_doc_index(), ["nonexistent"]) == []

    def test_empty_query_yields_empty(self) -> None:
        assert find(_two_doc_index(), []) == []

    def test_case_insensitive_lookup(self) -> None:
        results = find(_two_doc_index(), ["HELLO"])
        assert len(results) == 2

    def test_score_equals_total_matched_frequency(self) -> None:
        results = find(_two_doc_index(), ["hello"])
        for result in results:
            assert result.score == 1.0

    def test_results_ranked_by_score_descending(self) -> None:
        index = SearchIndex(
            metadata=IndexMetadata(
                base_url="https://x/",
                created_at="2026-05-07T12:34:56Z",
                page_count=2,
                total_tokens=10,
                unique_terms=1,
                politeness_delay_seconds=6.0,
            ),
            documents={
                "doc_001": Document(url="https://x/a", title="A", length=5),
                "doc_002": Document(url="https://x/b", title="B", length=5),
            },
            index={
                "hello": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=3, positions=[0, 1, 2]),
                },
            },
        )
        results = find(index, ["hello"])
        assert results[0].doc_id == "doc_002"
        assert results[1].doc_id == "doc_001"
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_matched_terms_recorded_per_document(self) -> None:
        results = find(_two_doc_index(), ["hello", "world"])
        assert results[0].matched_terms == {"hello": 1, "world": 1}
