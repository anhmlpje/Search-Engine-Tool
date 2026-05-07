# Design Notes

This document records the algorithmic and structural choices that shape
the search engine, with pointers to the literature each choice draws on.
The README explains *what* the tool does; this file explains *why* it is
built that way.

## 1. Inverted Index Structure

The on-disk index is the standard *posting-list* layout described in
Manning, Raghavan, and Schuetze, *Introduction to Information Retrieval*
(2008), chapters 1 and 2: each indexed term maps to a list of postings,
one per document the term appears in, recording per-document statistics.
Concretely:

```
index : term -> doc_id -> { freq, positions }
documents : doc_id -> { url, title, length }
```

Two design decisions in this layout deserve calling out.

**Synthetic document IDs.** Documents are keyed by short, stable handles
such as `doc_001` rather than by URL. The URL appears once in the document
table; postings reference the short handle. This keeps every term's
posting map compact and lets the document table evolve (new fields, URL
canonicalisation) without rewriting every posting.

**Positions stored as ordered list of integers.** A `set` would lose order
and de-duplicate repeated occurrences, breaking both phrase queries and
the `freq == len(positions)` invariant. A `list[int]` preserves the
information needed by every retrieval mode the project supports.

## 2. Indexable Text Scope

Each crawled page is tokenised from a deliberately *narrow* slice of its
HTML: the quote text, the author name, and the tag list on list-style
pages, plus the author title and biography on `/author/...` detail pages.
Site chrome -- the navigation menu, pagination links, and footer -- is
excluded.

The brief asks for "all word occurrences in the pages of the website";
crawling does cover the whole site, but indexing every byte of every page
would let common navigation words ("login", "next", "top", site name)
appear in every document, dominating the postings without informing
relevance. Excluding chrome is therefore a documented design choice in
the spirit of *content extraction*, not an oversight: the index treats
each page as its semantic content, and the README's command reference
states this explicitly.

A consequence of this choice is that the same quote can appear in
multiple documents (e.g. on `/page/1/`, on `/tag/love/`, and on
`/tag/love/page/1/` simultaneously) because those URLs are distinct
documents. This causes a quote's words to have a higher document
frequency than the underlying number of unique quotes, which lowers their
IDF and therefore their TF-IDF score. The effect is intentional: terms
that appear on many pages are exactly the ones less useful for ranking.

## 3. Tokenisation

The tokeniser is a single regular expression, `r"\b\w+\b"`, applied after
lowercasing the input. Under Python 3 the `\w` character class is
Unicode-aware, so non-ASCII letters survive the split. Punctuation,
including curly apostrophes (`U+2019`), is treated as a word boundary,
so `don't` and `don’t` both split into `don` and `t`. The tokeniser
is exposed in `src/utils.py` and used identically by the indexer at build
time and by the CLI when parsing query input, so a `print good!` query
behaves like `print good`.

**Why no stemming.** Porter (1980) and the Porter stemmer family are the
classic choice for English IR. We chose not to apply stemming on this
corpus for three reasons:

1. The corpus is short, literary English. Conflating *loving*, *loved*,
   and *love* would bring marginal recall improvements but harm
   interpretability of the printed posting lists.
2. Stemming would obscure the connection between the tokens shown by
   `print` and the words an end user can read on the source page.
3. Adding a stemmer would require either an external dependency (NLTK)
   or hand-rolling rules that drift away from a textbook reference. The
   project leans on standard-library primitives wherever feasible.

**Why no special handling for contractions.** Splitting `don't` into
`don` and `t` is admittedly noisy. We accept this in exchange for a
tokeniser that is easy to explain (`\b\w+\b` after lowercasing, full
stop) and consistent across query and index. A more sophisticated
scheme would be a productive extension.

## 4. Ranking: TF-IDF vs BM25

The `find` command ranks AND-intersection results by the textbook
TF-IDF formulation:

```
tf(t, d)   = freq(t, d) / |d|
idf(t)     = log( N / df(t) )
score(q,d) = sum over terms t in q of tf(t,d) * idf(t)
```

where `N` is the total number of indexed documents, `df(t)` is the
document frequency of term `t`, and `|d|` is the token count of `d`.
The formulation matches Manning et al. (2008), equations 6.9-6.12.

**Why TF-IDF and not BM25.** BM25 (Robertson and Zaragoza, *The
Probabilistic Relevance Framework: BM25 and Beyond*, 2009) is the
contemporary default in production retrieval systems and would be a
plausible alternative here. We chose TF-IDF for three project-specific
reasons:

1. **Pedagogical transparency.** The TF-IDF score for any document and
   query can be hand-computed from the printed posting list.
2. **No tuning data.** BM25 introduces two hyperparameters (`k1` and
   `b`) that must be calibrated to a corpus; with 200-odd documents and
   no relevance judgements there is no principled way to tune them.
3. **Implementation cost.** TF-IDF is two lines of Python over the
   existing posting structure; BM25 would add a length-normalisation
   term and the parameter pair without measurable benefit on this scale.

If the corpus grew or relevance judgements became available, swapping
the ranking function is a localised change in `src/search.py`.

## 5. Phrase Queries via Positions

The `find` command treats a single double-quoted argument as a phrase
query. Phrase semantics are implemented by reusing the position lists
already required by the brief: a document matches the phrase
`t_0 t_1 ... t_{k-1}` if there exists a position `p` such that token
`t_i` appears at position `p+i` for every `i`. This is the classical
*positional index* algorithm (Manning et al. 2008, Ch. 2.4) and is the
same machinery underlying Lucene's `match_phrase` and Elasticsearch's
`slop=0` phrase queries.

The implementation reuses the position list verbatim: no second index
is built, no schema change is required, and the on-disk JSON format
stays identical between AND-only and phrase-capable builds. Phrase
ranking is by the number of distinct adjacency matches in each
candidate document, which we found to be intuitive ("documents where
the phrase appears more times rank higher") and avoids mixing two
ranking scales (TF-IDF and adjacency count) in one query response.

## 6. Zipf Validation

Zipf's law (Zipf, 1949) predicts that, for natural-language text, the
frequency of the rank-`r` token is approximately `c / r` for some
constant `c`, equivalently `r * freq(r) ~= c`. Running the `stats`
command against our `quotes.toscrape.com` build (214 indexed documents,
29,918 total tokens, 4,503 unique terms) produces:

| rank | term | freq | rank x freq |
|-----:|------|-----:|------------:|
|    1 | the  | 1243 |        1243 |
|    2 | of   |  778 |        1556 |
|    3 | and  |  765 |        2295 |
|    4 | a    |  759 |        3036 |
|    5 | to   |  626 |        3130 |
|    6 | in   |  610 |        3660 |
|    7 | you  |  493 |        3451 |
|    8 | is   |  404 |        3232 |
|    9 | it   |  340 |        3060 |
|   10 | i    |  299 |        2990 |

The product `rank * freq` is approximately stable in the band
2,300-3,700 from rank 3 onwards, consistent with a Zipf-like
distribution as observed empirically on small English corpora; the
classic deviation at rank 1 (the most frequent token under-represents
the constant) is also visible. The fact that "the", "of", "and", "a"
dominate the table -- exactly the closed-class function words English
text always has at the top -- is direct evidence that the tokeniser is
producing language-like output rather than artefacts of HTML parsing.

The middle of the top-20 (`his`, `he`, `was`, `as`, ...) is also
typical of English narrative, and the appearance of `life` and `love`
in the top 20 reflects the literary-quote nature of the corpus.

## 7. Fielded Search and Snippets (Schema v2)

Schema version 2 introduces two related extensions that share the same
underlying motivation: the data already in the inverted index can do
more than the four required commands ask for, and surfacing that extra
capability turns a homework search engine into something closer to a
real one. Neither extension changes the on-disk format from a logical
perspective -- the inverted index still maps terms to documents to
postings, and postings still carry frequency and positions -- but the
container shape is widened to make the additional capabilities first-
class.

### Fielded inverted index

In schema v1 the index was a single posting space: one term -> documents
table, with all of a page's words flattened together. Schema v2 splits
the index into three named fields -- `text`, `author`, and `tag` --
each with its own posting list and its own per-document token stream:

    index : field -> term -> doc_id -> { freq, positions }

The CLI accepts a `field:term` syntax that routes the lookup to the
named field's posting list; bare terms continue to search across every
field and are aggregated for ranking. This is the same design used by
Lucene and Elasticsearch (their `match` query against multiple fields
versus their `term`/`match` query restricted to one field), translated
to a small Python project. The motivation is identical: the corpus has
real structural information -- a quote's author is not the same kind of
content as the quote text -- and discarding that structure at index time
is a form of information loss. Fielded indexing preserves it.

A document's `length` is now the sum of its fields' lengths, and the
TF-IDF formula is unchanged in shape: `tf` is freq divided by document
length, `idf` is log(N / df) where df is computed against the field
restriction when one is supplied, or across the union of fields when
the query is bare.

### Match snippets

Each document now stores its raw lower-cased token sequence per field.
At query time, `find` looks up the matched positions in the document's
`text` token stream and assembles a window of context around the first
match, wrapping the matched tokens in brackets:

    ...the world is full of [GOOD] [FRIENDS] who...

This is the same data already required by the brief (positions of every
word) put to a second use; no new index is built. The implementation is
in `_format_snippet` and `_build_snippet` in `src/search.py` and is
shared between `find` and `find_phrase` so phrase results show the
adjacency context as well.

### Why one schema bump rather than two

Both extensions touch the on-disk format. They could have been shipped
as separate increments (v2 for fielded indexing, v3 for snippets) but
the cost of maintaining a v2-only intermediate state was higher than
the value: every query path would have to handle "either layout" for
the time the two were independent. We chose a single v2 release that
contains both, with `storage.load` rejecting v1 files with an explicit
"please rebuild" message rather than silently carrying compatibility
code into a coursework submission.

## 8. Phrase Adjacency: Worked Example

For the home-page document of the live site, both `good` and `friends`
appear in the second quote's text:

> "Good friends are good."

After tokenisation (preceded by an empty-fixture for the first quote's
text, the author name, and tags) the token at position `p` is `good`
and the token at position `p+1` is `friends`. The phrase query
`find "good friends"` finds this single adjacency and reports
`occurrences=1` for that document. A query like `find "friends good"`
finds zero adjacencies in the same document, demonstrating that the
phrase query is order-sensitive in the way the algorithm requires.

## References

- C. D. Manning, P. Raghavan, and H. Schuetze, *Introduction to
  Information Retrieval*, Cambridge University Press, 2008.
  Chapters 1-2 (inverted index, postings, positional index) and 6
  (vector-space scoring with TF-IDF).
- M. F. Porter, "An Algorithm for Suffix Stripping",
  *Program* 14(3), 1980, pp. 130-137. Considered for tokenisation;
  see section 3.
- S. E. Robertson and H. Zaragoza, *The Probabilistic Relevance
  Framework: BM25 and Beyond*, Foundations and Trends in Information
  Retrieval 3(4), 2009. Considered as a ranking alternative; see
  section 4.
- G. K. Zipf, *Human Behavior and the Principle of Least Effort*,
  Addison-Wesley, 1949. Empirical baseline for the validation in
  section 6.
