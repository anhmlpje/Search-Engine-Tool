"""Tests for src.search."""

import math

from src.models import Document, IndexMetadata, Posting, SearchIndex
from src.search import find, find_phrase, print_word


# --- Fixtures ---------------------------------------------------------------


def _two_doc_index() -> SearchIndex:
    """Tiny index with three terms across two documents."""
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
            "world": {"doc_001": Posting(freq=1, positions=[1])},
            "friends": {"doc_002": Posting(freq=1, positions=[1])},
        },
    )


def _three_doc_tfidf_index() -> SearchIndex:
    """Three documents engineered so TF-IDF ranking is hand-computable.

    doc_001 = "good good cat"   (length 3; good x2, cat x1)
    doc_002 = "good dog"        (length 2; good x1, dog x1)
    doc_003 = "cat dog"         (length 2; cat x1, dog x1)

    For the query [good]:
      idf(good) = log(3/2)
      tf(good, doc_001) = 2/3 -> score = (2/3) * log(3/2)
      tf(good, doc_002) = 1/2 -> score = (1/2) * log(3/2)
      doc_001 must rank above doc_002.
    """
    return SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=3,
            total_tokens=7,
            unique_terms=3,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(url="https://x/a", title="A", length=3),
            "doc_002": Document(url="https://x/b", title="B", length=2),
            "doc_003": Document(url="https://x/c", title="C", length=2),
        },
        index={
            "good": {
                "doc_001": Posting(freq=2, positions=[0, 1]),
                "doc_002": Posting(freq=1, positions=[0]),
            },
            "cat": {
                "doc_001": Posting(freq=1, positions=[2]),
                "doc_003": Posting(freq=1, positions=[0]),
            },
            "dog": {
                "doc_002": Posting(freq=1, positions=[1]),
                "doc_003": Posting(freq=1, positions=[1]),
            },
        },
    )


def _phrase_index() -> SearchIndex:
    """Three documents engineered for phrase tests.

    doc_001: "good friends are good"      -> "good friends" ADJACENT once at p=0
    doc_002: "good big friends"           -> good and friends present, NOT adjacent
    doc_003: "good friends and good friends" -> "good friends" ADJACENT twice
    """
    return SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=3,
            total_tokens=12,
            unique_terms=4,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(url="https://x/a", title="A", length=4),
            "doc_002": Document(url="https://x/b", title="B", length=3),
            "doc_003": Document(url="https://x/c", title="C", length=5),
        },
        index={
            "good": {
                "doc_001": Posting(freq=2, positions=[0, 3]),
                "doc_002": Posting(freq=1, positions=[0]),
                "doc_003": Posting(freq=2, positions=[0, 3]),
            },
            "friends": {
                "doc_001": Posting(freq=1, positions=[1]),
                "doc_002": Posting(freq=1, positions=[2]),
                "doc_003": Posting(freq=2, positions=[1, 4]),
            },
            "are": {"doc_001": Posting(freq=1, positions=[2])},
            "big": {"doc_002": Posting(freq=1, positions=[1])},
            "and": {"doc_003": Posting(freq=1, positions=[2])},
        },
    )


# --- print_word -------------------------------------------------------------


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
        assert out.index("doc_001") < out.index("doc_002")


# --- find -------------------------------------------------------------------


class TestFind:
    def test_single_term_returns_all_matching_docs(self) -> None:
        results = find(_two_doc_index(), ["hello"])
        assert {r.doc_id for r in results} == {"doc_001", "doc_002"}

    def test_multi_term_takes_intersection(self) -> None:
        results = find(_two_doc_index(), ["hello", "world"])
        assert len(results) == 1
        assert results[0].doc_id == "doc_001"

    def test_disjoint_terms_yield_empty(self) -> None:
        assert find(_two_doc_index(), ["world", "friends"]) == []

    def test_unknown_term_yields_empty(self) -> None:
        assert find(_two_doc_index(), ["nonexistent"]) == []

    def test_empty_query_yields_empty(self) -> None:
        assert find(_two_doc_index(), []) == []

    def test_case_insensitive_lookup(self) -> None:
        results = find(_two_doc_index(), ["HELLO"])
        assert len(results) == 2

    def test_matched_terms_recorded_per_document(self) -> None:
        results = find(_two_doc_index(), ["hello", "world"])
        assert results[0].matched_terms == {"hello": 1, "world": 1}


class TestTfIdfRanking:
    def test_denser_doc_ranks_higher_for_single_term(self) -> None:
        """doc_001 has good twice in length 3; doc_002 has good once in length 2.
        TF-IDF: (2/3) * log(3/2)  >  (1/2) * log(3/2). doc_001 must come first.
        """
        results = find(_three_doc_tfidf_index(), ["good"])
        assert [r.doc_id for r in results] == ["doc_001", "doc_002"]
        assert results[0].rank == 1
        assert results[1].rank == 2
        assert results[0].score > results[1].score

    def test_score_matches_hand_computed_value(self) -> None:
        results = find(_three_doc_tfidf_index(), ["good"])
        idf = math.log(3 / 2)
        expected_001 = (2 / 3) * idf
        expected_002 = (1 / 2) * idf
        scores = {r.doc_id: r.score for r in results}
        assert scores["doc_001"] == expected_001
        assert scores["doc_002"] == expected_002

    def test_term_in_every_doc_has_zero_idf(self) -> None:
        index = SearchIndex(
            metadata=IndexMetadata(
                base_url="https://x/",
                created_at="t",
                page_count=2,
                total_tokens=2,
                unique_terms=1,
                politeness_delay_seconds=6.0,
            ),
            documents={
                "doc_001": Document(url="https://x/a", title="A", length=1),
                "doc_002": Document(url="https://x/b", title="B", length=1),
            },
            index={
                "ubiquitous": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
            },
        )
        results = find(index, ["ubiquitous"])
        # idf = log(2/2) = 0 -> every score is 0
        for result in results:
            assert result.score == 0.0


# --- find_phrase ------------------------------------------------------------


class TestFindPhrase:
    def test_adjacent_match_returns_doc(self) -> None:
        results = find_phrase(_phrase_index(), "good friends")
        doc_ids = {r.doc_id for r in results}
        assert "doc_001" in doc_ids
        assert "doc_003" in doc_ids
        # doc_002 has both words but not adjacent -> excluded
        assert "doc_002" not in doc_ids

    def test_non_adjacent_does_not_match(self) -> None:
        # doc_002 is the negative case: "good big friends" -> excluded above.
        # Now also confirm a phrase not present anywhere returns empty.
        results = find_phrase(_phrase_index(), "friends good")  # reversed order
        assert results == []

    def test_ranks_by_occurrence_count(self) -> None:
        """doc_003 has the phrase twice; doc_001 once. doc_003 must rank first."""
        results = find_phrase(_phrase_index(), "good friends")
        assert results[0].doc_id == "doc_003"
        assert results[0].score == 2.0
        assert results[1].doc_id == "doc_001"
        assert results[1].score == 1.0

    def test_single_token_phrase_falls_back_to_find(self) -> None:
        # find_phrase("good") should behave as find(["good"])
        phrase_results = find_phrase(_phrase_index(), "good")
        find_results = find(_phrase_index(), ["good"])
        assert [r.doc_id for r in phrase_results] == [
            r.doc_id for r in find_results
        ]

    def test_unknown_token_yields_empty(self) -> None:
        assert find_phrase(_phrase_index(), "good xyzunknown") == []

    def test_empty_phrase_yields_empty(self) -> None:
        assert find_phrase(_phrase_index(), "") == []
        assert find_phrase(_phrase_index(), "    ") == []

    def test_case_insensitive(self) -> None:
        results = find_phrase(_phrase_index(), "GOOD FRIENDS")
        assert len(results) > 0
