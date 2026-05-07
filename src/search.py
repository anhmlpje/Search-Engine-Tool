"""Search operations over a built :class:`SearchIndex`.

Two query modes:

* :func:`find` -- AND intersection of bare terms, ranked by TF-IDF.
* :func:`find_phrase` -- adjacency-checked phrase matching, ranked by the
  number of phrase occurrences in each candidate document. Reuses the
  position lists already required by the core spec; no extra index is built.

The classic textbook TF-IDF formulation is used so the math is easy to
explain in the design notes:

    tf(t, d)  = freq(t, d) / |d|
    idf(t)    = log(N / df(t))
    score(q, d) = sum over terms t in q of tf(t, d) * idf(t)
"""

import math
from dataclasses import dataclass, field

from src.models import SearchIndex
from src.utils import tokenize


@dataclass
class FindResult:
    """A single document matching a multi-term or phrase query."""

    doc_id: str
    url: str
    score: float
    matched_terms: dict[str, int] = field(default_factory=dict)
    rank: int = 0


# --- Single-word inspection -----------------------------------------------


def print_word(index: SearchIndex, word: str) -> str:
    """Return a human-readable view of the posting list for ``word``."""
    normalised = word.lower()
    postings = index.index.get(normalised)
    if not postings:
        return f"word: {normalised}\n  no matches"

    lines = [f"word: {normalised}", f"documents: {len(postings)}"]
    for doc_id in sorted(postings.keys()):
        posting = postings[doc_id]
        doc = index.documents[doc_id]
        lines.append(
            f"  {doc_id}  {doc.url}  freq={posting.freq}  positions={posting.positions}"
        )
    return "\n".join(lines)


# --- TF-IDF helpers -------------------------------------------------------


def _idf(index: SearchIndex, term: str) -> float:
    """Inverse document frequency: ``log(N / df(term))``.

    Returns ``0.0`` when the term is unknown so the caller does not need to
    special-case it.
    """
    n_docs = len(index.documents)
    if n_docs == 0:
        return 0.0
    df = len(index.index.get(term, {}))
    if df == 0:
        return 0.0
    return math.log(n_docs / df)


def _tf(freq: int, doc_length: int) -> float:
    """Normalised term frequency: ``freq / |d|``."""
    if doc_length <= 0:
        return 0.0
    return freq / doc_length


# --- AND query, TF-IDF ranked ---------------------------------------------


def find(index: SearchIndex, terms: list[str]) -> list[FindResult]:
    """Return documents containing every term in ``terms`` (AND semantics).

    Results are ranked by TF-IDF total score, breaking ties by ``doc_id``
    for stability. Empty queries and unknown terms produce an empty list
    rather than an error.
    """
    if not terms:
        return []

    normalised = [t.lower() for t in terms]
    posting_lists = []
    for term in normalised:
        postings = index.index.get(term)
        if not postings:
            return []
        posting_lists.append(postings)

    common: set[str] = set(posting_lists[0].keys())
    for postings in posting_lists[1:]:
        common &= set(postings.keys())

    results: list[FindResult] = []
    for doc_id in common:
        doc = index.documents[doc_id]
        score = 0.0
        matched: dict[str, int] = {}
        for i, term in enumerate(normalised):
            posting = posting_lists[i][doc_id]
            score += _tf(posting.freq, doc.length) * _idf(index, term)
            matched[term] = posting.freq
        results.append(
            FindResult(
                doc_id=doc_id, url=doc.url, score=score, matched_terms=matched
            )
        )

    results.sort(key=lambda r: (-r.score, r.doc_id))
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    return results


# --- Phrase query ---------------------------------------------------------


def find_phrase(index: SearchIndex, phrase: str) -> list[FindResult]:
    """Return documents containing ``phrase`` as adjacent tokens.

    A document matches if there exists a position ``p`` such that
    token[0] is at ``p``, token[1] at ``p+1``, ..., token[k-1] at ``p+k-1``.
    Matching documents are ranked by the number of distinct ``p`` for which
    that condition holds (more phrase occurrences -> higher score).

    Tokenisation here uses the same rules as the index, so case and
    punctuation behave identically to single-word queries.
    """
    tokens = tokenize(phrase)
    if not tokens:
        return []
    if len(tokens) == 1:
        return find(index, tokens)

    posting_lists = []
    for token in tokens:
        postings = index.index.get(token)
        if not postings:
            return []
        posting_lists.append(postings)

    common: set[str] = set(posting_lists[0].keys())
    for postings in posting_lists[1:]:
        common &= set(postings.keys())

    results: list[FindResult] = []
    for doc_id in common:
        first_positions = posting_lists[0][doc_id].positions
        rest_position_sets = [
            set(posting_lists[i][doc_id].positions) for i in range(1, len(tokens))
        ]

        occurrences = 0
        for p0 in first_positions:
            if all(
                (p0 + offset + 1) in rest_position_sets[offset]
                for offset in range(len(rest_position_sets))
            ):
                occurrences += 1

        if occurrences == 0:
            continue

        doc = index.documents[doc_id]
        matched = {
            token: posting_lists[i][doc_id].freq for i, token in enumerate(tokens)
        }
        results.append(
            FindResult(
                doc_id=doc_id,
                url=doc.url,
                score=float(occurrences),
                matched_terms=matched,
            )
        )

    results.sort(key=lambda r: (-r.score, r.doc_id))
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    return results
