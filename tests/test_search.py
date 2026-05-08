"""Tests for src.search."""

import math

from src.models import (
    Document,
    FieldData,
    IndexMetadata,
    Posting,
    SearchIndex,
)
from src.search import find, find_phrase, print_word


def _empty_fields() -> dict[str, FieldData]:
    return {
        "text": FieldData(length=0, tokens=[]),
        "author": FieldData(length=0, tokens=[]),
        "tag": FieldData(length=0, tokens=[]),
    }


def _two_doc_index() -> SearchIndex:
    """Tiny fielded index used by most tests below."""
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
            "doc_001": Document(
                url="https://x/a",
                title="A",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["hello", "world"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/b",
                title="B",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["hello", "friends"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
                "hello": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
                "world": {"doc_001": Posting(freq=1, positions=[1])},
                "friends": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "author": {},
            "tag": {},
        },
    )


def _three_doc_tfidf_index() -> SearchIndex:
    """Three text-field documents engineered so TF-IDF ranking is hand-computable.

    doc_001 text = "good good cat"   (length 3; good x2, cat x1)
    doc_002 text = "good dog"        (length 2; good x1, dog x1)
    doc_003 text = "cat dog"         (length 2; cat x1, dog x1)
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
            "doc_001": Document(
                url="https://x/a",
                title="A",
                length=3,
                fields={
                    "text": FieldData(length=3, tokens=["good", "good", "cat"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/b",
                title="B",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["good", "dog"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_003": Document(
                url="https://x/c",
                title="C",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["cat", "dog"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
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
            "author": {},
            "tag": {},
        },
    )


def _phrase_index() -> SearchIndex:
    """Three text-field documents engineered for phrase tests.

    doc_001: "good friends are good"          -> "good friends" adjacent once at p=0
    doc_002: "good big friends"                -> good and friends present, NOT adjacent
    doc_003: "good friends and good friends"   -> "good friends" adjacent twice
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
            "doc_001": Document(
                url="https://x/a",
                title="A",
                length=4,
                fields={
                    "text": FieldData(
                        length=4, tokens=["good", "friends", "are", "good"]
                    ),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/b",
                title="B",
                length=3,
                fields={
                    "text": FieldData(length=3, tokens=["good", "big", "friends"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_003": Document(
                url="https://x/c",
                title="C",
                length=5,
                fields={
                    "text": FieldData(
                        length=5,
                        tokens=["good", "friends", "and", "good", "friends"],
                    ),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
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
            "author": {},
            "tag": {},
        },
    )


def _fielded_index() -> SearchIndex:
    """Fielded documents for testing field:term query syntax."""
    return SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=2,
            total_tokens=8,
            unique_terms=4,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(
                url="https://x/wilde-love",
                title="Wilde",
                length=4,
                fields={
                    "text": FieldData(length=2, tokens=["love", "endures"]),
                    "author": FieldData(length=2, tokens=["oscar", "wilde"]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/twain-love",
                title="Twain",
                length=4,
                fields={
                    "text": FieldData(length=2, tokens=["love", "wins"]),
                    "author": FieldData(length=2, tokens=["mark", "twain"]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
                "love": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
                "endures": {"doc_001": Posting(freq=1, positions=[1])},
                "wins": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "author": {
                "oscar": {"doc_001": Posting(freq=1, positions=[0])},
                "wilde": {"doc_001": Posting(freq=1, positions=[1])},
                "mark": {"doc_002": Posting(freq=1, positions=[0])},
                "twain": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "tag": {},
        },
    )


# --- print_word -------------------------------------------------------------


class TestPrintWord:
    def test_word_present_lists_documents_per_field(self) -> None:
        out = print_word(_two_doc_index(), "hello")
        assert "hello" in out
        assert "field: text" in out
        assert "doc_001" in out
        assert "doc_002" in out
        assert "freq=1" in out

    def test_word_absent_returns_no_matches(self) -> None:
        out = print_word(_two_doc_index(), "missing")
        assert "no matches" in out

    def test_case_insensitive_lookup(self) -> None:
        out = print_word(_two_doc_index(), "HELLO")
        assert "doc_001" in out

    def test_lists_multiple_fields(self) -> None:
        out = print_word(_fielded_index(), "love")
        assert "field: text" in out


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

    def test_punctuated_input_tokenised(self) -> None:
        # 'hello!' tokenises to 'hello' before lookup
        results = find(_two_doc_index(), ["hello!"])
        assert len(results) == 2

    def test_matched_terms_recorded_per_document(self) -> None:
        results = find(_two_doc_index(), ["hello", "world"])
        assert results[0].matched_terms == {"hello": 1, "world": 1}

    def test_snippet_built_from_text_field(self) -> None:
        results = find(_two_doc_index(), ["hello"])
        for result in results:
            # both docs have 'hello' at text position 0; snippet wraps it.
            assert "[HELLO]" in result.snippet


class TestTfIdfRanking:
    def test_denser_doc_ranks_higher_for_single_term(self) -> None:
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
                "doc_001": Document(
                    url="https://x/a",
                    title="A",
                    length=1,
                    fields={
                        "text": FieldData(length=1, tokens=["ubiquitous"]),
                        "author": FieldData(length=0, tokens=[]),
                        "tag": FieldData(length=0, tokens=[]),
                    },
                ),
                "doc_002": Document(
                    url="https://x/b",
                    title="B",
                    length=1,
                    fields={
                        "text": FieldData(length=1, tokens=["ubiquitous"]),
                        "author": FieldData(length=0, tokens=[]),
                        "tag": FieldData(length=0, tokens=[]),
                    },
                ),
            },
            index={
                "text": {
                    "ubiquitous": {
                        "doc_001": Posting(freq=1, positions=[0]),
                        "doc_002": Posting(freq=1, positions=[0]),
                    },
                },
                "author": {},
                "tag": {},
            },
        )
        results = find(index, ["ubiquitous"])
        for result in results:
            assert result.score == 0.0


# --- Fielded queries --------------------------------------------------------


class TestFieldedQueries:
    def test_field_prefix_restricts_lookup(self) -> None:
        # 'love' appears in both docs' text field; restrict to author and
        # neither doc has it as an author -> empty.
        assert find(_fielded_index(), ["author:love"]) == []

    def test_field_query_returns_correct_doc(self) -> None:
        results = find(_fielded_index(), ["author:wilde"])
        assert len(results) == 1
        assert results[0].doc_id == "doc_001"

    def test_combined_bare_and_field(self) -> None:
        # love is in both docs (text field); narrowing by author:wilde
        # filters to doc_001 only.
        results = find(_fielded_index(), ["love", "author:wilde"])
        assert len(results) == 1
        assert results[0].doc_id == "doc_001"

    def test_unknown_field_yields_empty(self) -> None:
        assert find(_fielded_index(), ["unknown_field:love"]) == []

    def test_matched_label_includes_field_prefix(self) -> None:
        results = find(_fielded_index(), ["love", "author:wilde"])
        assert "love" in results[0].matched_terms
        assert "author:wilde" in results[0].matched_terms


# --- find_phrase ------------------------------------------------------------


class TestFindPhrase:
    def test_adjacent_match_returns_doc(self) -> None:
        results = find_phrase(_phrase_index(), "good friends")
        doc_ids = {r.doc_id for r in results}
        assert "doc_001" in doc_ids
        assert "doc_003" in doc_ids
        # doc_002 has both words but not adjacent
        assert "doc_002" not in doc_ids

    def test_non_adjacent_does_not_match(self) -> None:
        # reversed phrase finds nothing in any doc
        results = find_phrase(_phrase_index(), "friends good")
        assert results == []

    def test_ranks_by_occurrence_count(self) -> None:
        results = find_phrase(_phrase_index(), "good friends")
        assert results[0].doc_id == "doc_003"
        assert results[0].score == 2.0
        assert results[1].doc_id == "doc_001"
        assert results[1].score == 1.0

    def test_single_token_phrase_falls_back_to_find(self) -> None:
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

    def test_phrase_snippet_highlights_phrase_tokens(self) -> None:
        results = find_phrase(_phrase_index(), "good friends")
        for result in results:
            assert "[GOOD]" in result.snippet
            assert "[FRIENDS]" in result.snippet

    def test_phrase_results_have_no_breakdown(self) -> None:
        # Phrase score is an occurrence count, not a TF-IDF sum.
        results = find_phrase(_phrase_index(), "good friends")
        for result in results:
            assert result.breakdown == []


# --- Explain breakdown ------------------------------------------------------


class TestExplainBreakdown:
    def test_breakdown_matches_hand_computed_values(self) -> None:
        # Same fixture as TestTfIdfRanking. doc_001 has good x2 in length 3.
        results = find(_three_doc_tfidf_index(), ["good"])
        idf_good = math.log(3 / 2)
        result_001 = next(r for r in results if r.doc_id == "doc_001")
        assert len(result_001.breakdown) == 1
        contribution = result_001.breakdown[0]
        assert contribution.label == "good"
        assert contribution.freq == 2
        assert contribution.tf == 2 / 3
        assert contribution.idf == idf_good
        assert contribution.tfidf == (2 / 3) * idf_good

    def test_breakdown_sums_to_score(self) -> None:
        # The result.score is the sum of per-term tfidf contributions.
        results = find(_two_doc_index(), ["hello", "world"])
        for result in results:
            total = sum(c.tfidf for c in result.breakdown)
            assert result.score == total

    def test_breakdown_label_includes_field_prefix(self) -> None:
        results = find(_fielded_index(), ["love", "author:wilde"])
        labels = [c.label for c in results[0].breakdown]
        assert "love" in labels
        assert "author:wilde" in labels

    def test_breakdown_present_for_every_query_term(self) -> None:
        results = find(_three_doc_tfidf_index(), ["good", "cat"])
        # Only doc_001 has both; one breakdown entry per query term.
        assert len(results) == 1
        assert len(results[0].breakdown) == 2
