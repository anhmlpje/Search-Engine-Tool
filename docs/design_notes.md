# Design Notes

Algorithmic rationale and references for the search engine implementation.
This document is filled in incrementally as each phase lands; the headings
below mark the sections each phase will populate.

## 1. Inverted Index Structure

*To be written in Phase 2.* Posting layout (term -> doc_id -> freq + positions),
references to Manning, Raghavan, and Schuetze, *Introduction to Information
Retrieval* (2008).

## 2. Indexable Text Scope

*To be written in Phase 2.* Why the indexer extracts quote text, author, and
tags rather than full page text. Walks through the navigation/pagination
pollution problem and the design decision to surface scope explicitly.

## 3. Tokenisation

*To be written in Phase 1.* Regex choice (`\b\w+\b`), lowercasing, treatment
of curly apostrophes, Unicode handling. Why no stemming on this corpus.

## 4. Ranking: TF-IDF vs BM25

*To be written in Phase 4.* Why TF-IDF was chosen over BM25 for a small
corpus, and what the implementation looks like.

## 5. Phrase Queries via Positions

*To be written in Phase 4.* How phrase matching reuses the position lists
without a second index.

## 6. Zipf Validation

*To be written in Phase 5.* Empirical observation from the `stats` command,
checked against Zipf's distribution.

## 7. Extensions (Optional)

*To be written in Phase 6 if extensions ship.* Fielded search, snippet
generation, and the `--explain` mode -- how each reuses existing data
rather than duplicating it.

## References

*To be filled in alongside the sections above.*
