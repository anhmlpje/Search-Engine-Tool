"""Search operations over a built :class:`SearchIndex`.

Phase 3 ships :func:`print_word` for single-word inspection and a basic
:func:`find` that AND-intersects postings and ranks results by total
matched-term frequency. Phase 4 swaps the ranking formula for TF-IDF and
adds phrase queries, but keeps this same shape and signature.
"""

from dataclasses import dataclass, field

from src.models import SearchIndex


@dataclass
class FindResult:
    """A single document matching a multi-word query."""

    doc_id: str
    url: str
    score: float
    matched_terms: dict[str, int] = field(default_factory=dict)
    rank: int = 0


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


def find(index: SearchIndex, terms: list[str]) -> list[FindResult]:
    """Return documents containing every term in ``terms`` (AND semantics).

    The result list is ranked by total matched-term frequency in each
    document, breaking ties by ``doc_id`` for stability. Empty queries and
    unknown terms produce an empty result list rather than an error.
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
        matched = {
            term: posting_lists[i][doc_id].freq
            for i, term in enumerate(normalised)
        }
        score = float(sum(matched.values()))
        doc = index.documents[doc_id]
        results.append(
            FindResult(
                doc_id=doc_id,
                url=doc.url,
                score=score,
                matched_terms=matched,
            )
        )

    results.sort(key=lambda r: (-r.score, r.doc_id))
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    return results
