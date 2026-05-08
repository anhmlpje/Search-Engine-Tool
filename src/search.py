"""Search operations over a fielded :class:`SearchIndex`.

Two query modes:

* :func:`find` -- AND intersection of bare or ``field:term`` items, ranked
  by TF-IDF. A bare term searches across every field; a ``field:term``
  item restricts the lookup to that field's posting list. Each result
  carries a context snippet drawn from the document's stored ``text``
  tokens when available.

* :func:`find_phrase` -- adjacency-checked phrase matching against the
  ``text`` field. Reuses the position lists already required by the core
  spec; no extra index is built. Phrase results are ranked by the number
  of phrase occurrences in each candidate document.

The classic textbook TF-IDF formulation is used so the math is easy to
explain in the design notes:

    tf(t, d)     = freq(t, d) / |d|
    idf(t)       = log(N / df(t))
    score(q, d)  = sum over query items of tf * idf
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from src.models import Posting, SearchIndex
from src.utils import tokenize

SNIPPET_WINDOW = 6


@dataclass
class TermContribution:
    """Per-term TF-IDF arithmetic for one document, for ``--explain`` mode."""

    label: str  # bare term, e.g. "good", or fielded, e.g. "author:wilde"
    freq: int
    tf: float
    idf: float
    tfidf: float


@dataclass
class FindResult:
    """A single document matching a query."""

    doc_id: str
    url: str
    score: float
    matched_terms: dict[str, int] = field(default_factory=dict)
    rank: int = 0
    snippet: str = ""
    breakdown: list[TermContribution] = field(default_factory=list)


# --- Single-word inspection -----------------------------------------------


def print_word(index: SearchIndex, word: str) -> str:
    """Return a human-readable view of every posting for ``word`` across
    every field. Useful for confirming which field a term lives in.
    """
    normalised = word.lower()
    field_hits: list[tuple[str, dict[str, Posting]]] = []
    for field_name, field_index in index.index.items():
        postings = field_index.get(normalised)
        if postings:
            field_hits.append((field_name, postings))

    if not field_hits:
        return f"word: {normalised}\n  no matches"

    total_docs = sum(len(p) for _, p in field_hits)
    lines = [f"word: {normalised}", f"documents: {total_docs} (across fields)"]
    for field_name, postings in field_hits:
        lines.append(f"  field: {field_name}")
        for doc_id in sorted(postings.keys()):
            posting = postings[doc_id]
            doc = index.documents[doc_id]
            lines.append(
                f"    {doc_id}  {doc.url}  freq={posting.freq}  "
                f"positions={posting.positions}"
            )
    return "\n".join(lines)


# --- Query-item parsing ---------------------------------------------------


def _parse_query_item(raw: str) -> tuple[str | None, str]:
    """Parse ``field:term`` or ``term``.

    Returns ``(field, term)`` where ``field`` is ``None`` for bare terms,
    or the lower-cased field name otherwise. The term half is run
    through the same tokeniser used at index time and the first emitted
    token is returned; if tokenisation produces nothing, an empty term
    is returned and the caller treats it as a no-op.
    """
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        prefix_tokens = tokenize(prefix)
        rest_tokens = tokenize(rest)
        if prefix_tokens and rest_tokens:
            return (prefix_tokens[0], rest_tokens[0])
    bare_tokens = tokenize(raw)
    if bare_tokens:
        return (None, bare_tokens[0])
    return (None, "")


# --- TF-IDF helpers -------------------------------------------------------


def _tf(freq: int, doc_length: int) -> float:
    if doc_length <= 0:
        return 0.0
    return freq / doc_length


def _idf(index: SearchIndex, query_field: str | None, term: str) -> float:
    """Inverse document frequency.

    For a bare term (``query_field is None``) the document frequency is
    the number of distinct documents containing the term in *any* field.
    For a fielded query, the count is restricted to that field.
    """
    n_docs = len(index.documents)
    if n_docs == 0:
        return 0.0
    if query_field is not None:
        df = len(index.index.get(query_field, {}).get(term, {}))
    else:
        doc_set: set[str] = set()
        for field_index in index.index.values():
            doc_set.update(field_index.get(term, {}).keys())
        df = len(doc_set)
    if df == 0:
        return 0.0
    return math.log(n_docs / df)


def _resolve_postings(
    index: SearchIndex, query_field: str | None, term: str
) -> dict[str, dict[str, Posting]]:
    """Return ``doc_id -> {field_name: Posting}`` for matches of ``term``.

    Bare terms aggregate matches across every field; fielded queries
    restrict the lookup to the named field. An unknown field name yields
    an empty result.
    """
    out: dict[str, dict[str, Posting]] = {}
    if query_field is not None:
        for doc_id, posting in index.index.get(query_field, {}).get(term, {}).items():
            out[doc_id] = {query_field: posting}
        return out
    for field_name, field_index in index.index.items():
        for doc_id, posting in field_index.get(term, {}).items():
            out.setdefault(doc_id, {})[field_name] = posting
    return out


# --- Snippet generation ---------------------------------------------------


def _format_snippet(
    tokens: list[str], highlight_positions: Iterable[int], window: int
) -> str:
    if not tokens:
        return ""
    positions = sorted(set(highlight_positions))
    if not positions:
        return ""
    first = positions[0]
    start = max(0, first - window)
    end = min(len(tokens), first + window + 1)
    pieces = []
    for i in range(start, end):
        if i in positions:
            pieces.append(f"[{tokens[i].upper()}]")
        else:
            pieces.append(tokens[i])
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(tokens) else ""
    return f"{prefix}{' '.join(pieces)}{suffix}"


def _build_snippet(
    index: SearchIndex,
    doc_id: str,
    parsed_items: list[tuple[str | None, str]],
    per_item_postings: list[dict[str, dict[str, Posting]]],
) -> str:
    """Build a snippet for ``doc_id`` highlighting every match in the
    text field. Returns an empty string when no text-field match exists
    for this document; in that case the caller relies on URL alone.
    """
    doc = index.documents.get(doc_id)
    if doc is None:
        return ""
    text_field = doc.fields.get("text")
    if text_field is None or not text_field.tokens:
        return ""

    text_positions: set[int] = set()
    for i, (query_field, _term) in enumerate(parsed_items):
        if query_field is not None and query_field != "text":
            continue
        per_field = per_item_postings[i].get(doc_id, {})
        text_posting = per_field.get("text")
        if text_posting is not None:
            text_positions.update(text_posting.positions)

    if not text_positions:
        return ""
    return _format_snippet(text_field.tokens, text_positions, SNIPPET_WINDOW)


# --- AND query, TF-IDF ranked ---------------------------------------------


def find(index: SearchIndex, items: list[str]) -> list[FindResult]:
    """Return documents matching every query item, ranked by TF-IDF.

    Each input string is either a bare term (searched across all fields)
    or a ``field:term`` token (restricted to one field). Empty queries,
    unknown terms, and unknown field names produce an empty result list.
    """
    if not items:
        return []

    parsed = [_parse_query_item(raw) for raw in items]
    parsed = [(f, t) for (f, t) in parsed if t]
    if not parsed:
        return []

    per_item_postings: list[dict[str, dict[str, Posting]]] = []
    for query_field, term in parsed:
        postings = _resolve_postings(index, query_field, term)
        if not postings:
            return []
        per_item_postings.append(postings)

    common: set[str] = set(per_item_postings[0].keys())
    for postings in per_item_postings[1:]:
        common &= set(postings.keys())

    results: list[FindResult] = []
    for doc_id in common:
        doc = index.documents[doc_id]
        score = 0.0
        matched: dict[str, int] = {}
        breakdown: list[TermContribution] = []
        for i, (query_field, term) in enumerate(parsed):
            field_postings = per_item_postings[i][doc_id]
            term_freq = sum(p.freq for p in field_postings.values())
            tf_val = _tf(term_freq, doc.length)
            idf_val = _idf(index, query_field, term)
            tfidf_val = tf_val * idf_val
            score += tfidf_val
            label = f"{query_field}:{term}" if query_field else term
            matched[label] = term_freq
            breakdown.append(
                TermContribution(
                    label=label,
                    freq=term_freq,
                    tf=tf_val,
                    idf=idf_val,
                    tfidf=tfidf_val,
                )
            )
        snippet = _build_snippet(index, doc_id, parsed, per_item_postings)
        results.append(
            FindResult(
                doc_id=doc_id,
                url=doc.url,
                score=score,
                matched_terms=matched,
                snippet=snippet,
                breakdown=breakdown,
            )
        )

    results.sort(key=lambda r: (-r.score, r.doc_id))
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    return results


# --- Phrase query (text field only) ---------------------------------------


def find_phrase(index: SearchIndex, phrase: str) -> list[FindResult]:
    """Match ``phrase`` as adjacent tokens in the *text* field only.

    The phrase scan ignores ``author`` and ``tag`` fields because phrase
    semantics over short author names or single-token tags are rarely
    useful and would complicate the position arithmetic.
    """
    tokens = tokenize(phrase)
    if not tokens:
        return []
    if len(tokens) == 1:
        return find(index, tokens)

    text_index = index.index.get("text", {})
    posting_lists: list[dict[str, Posting]] = []
    for token in tokens:
        postings = text_index.get(token)
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

        match_starts: list[int] = []
        for p0 in first_positions:
            if all(
                (p0 + offset + 1) in rest_position_sets[offset]
                for offset in range(len(rest_position_sets))
            ):
                match_starts.append(p0)

        if not match_starts:
            continue

        doc = index.documents[doc_id]
        matched = {
            token: posting_lists[i][doc_id].freq for i, token in enumerate(tokens)
        }
        text_field = doc.fields.get("text")
        snippet = ""
        if text_field is not None:
            highlight = set()
            for start in match_starts:
                for offset in range(len(tokens)):
                    highlight.add(start + offset)
            snippet = _format_snippet(text_field.tokens, highlight, SNIPPET_WINDOW)
        results.append(
            FindResult(
                doc_id=doc_id,
                url=doc.url,
                score=float(len(match_starts)),
                matched_terms=matched,
                snippet=snippet,
            )
        )

    results.sort(key=lambda r: (-r.score, r.doc_id))
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    return results
