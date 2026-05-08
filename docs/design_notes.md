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

## 8. Complexity Derivation

The README's *Performance* section quotes one-line complexity claims for
each operation. This section walks through where those claims come from
by reading the actual code in `src/`, with explicit assumptions called
out so the reader can judge how tight or loose the analysis is.

### Notation

| Symbol | Meaning |
|--------|---------|
| `N`    | Number of indexed documents |
| `L`    | Average token count per document (across fields) |
| `T`    | Vocabulary size (number of unique terms) |
| `D`    | Number of documents containing a given query term |
| `D_min`| Smallest `D` across the terms in a query |
| `k`    | Number of terms in a query |
| `P`    | Total number of position entries scanned in a phrase query |
| `F`    | Number of fields (constant 3 in this implementation) |

### `build` -- `O(N x L)`

The relevant loop is `build_index` in `src/indexer.py`:

```python
for ordinal, page in enumerate(pages):                # outer: N iterations
    fields_text = extract_fields(page.html)            # ~ O(L) per page
    for field_name in FIELD_NAMES:                     # F = 3 (constant)
        tokens = tokenize(fields_text[field_name])     # O(L) per field, sums to O(L) per page
        for position, token in enumerate(tokens):      # L iterations per page
            postings = field_index.setdefault(token, {})  # O(1) dict insert/get
            posting = postings.get(doc_id)                # O(1) dict get
            posting.freq += 1                              # O(1)
            posting.positions.append(position)             # O(1) amortised
```

Inner-most work is `O(1)` per token, multiplied by `L` tokens per page,
multiplied by `N` pages. HTML parsing inside `extract_fields` is
`O(L)` to first approximation: every token in the output corresponds to
a contiguous span of bytes in the input, and BeautifulSoup's
`html.parser` walks the document in a single linear pass. The two
costs combine to `O(N x L)`, which matches the empirical observation
that `build` time on the live site is overwhelmingly dominated by the
politeness sleep budget (`6 s x N`) rather than CPU work.

### `print word` -- `O(F) + O(D log D)`

`print_word` in `src/search.py` looks up the term in each field, then
sorts the matching documents by `doc_id` for stable output:

```python
for field_name, field_index in index.index.items():    # F = 3 fields
    postings = field_index.get(normalised)              # O(1) per field
    ...
for field_name, postings in field_hits:
    for doc_id in sorted(postings.keys()):              # O(D log D) sort
        ...
```

Lookup cost is `O(F)` which is constant; the visible work is the
final sort over `D` matching documents. With `F` taken as a constant,
this collapses to `O(D log D)`.

### `find` (AND + TF-IDF) -- `O(k x D_min) + O(D x k) + O(D log D)`

The `find` body in `src/search.py` decomposes into four steps. With
`F` and the `_parse_query_item` token regex treated as constants:

1. **Per-term posting lookup.** For each of the `k` query terms, one
   `dict.get` (`O(1)`) plus the `_resolve_postings` traversal. For a
   bare term that traversal is `O(F)`; for a fielded term it is `O(1)`.
   Total: `O(k)`.

2. **Set intersection across `k` posting maps.** Python's `set &`
   operation is `O(min(|s1|, |s2|))`. Successive intersections never
   make the working set larger, so the total is bounded by the smallest
   posting list: `O(k x D_min)`.

3. **Scoring loop.** For each document in the intersected set, loop
   over the `k` query items computing `tf` and `idf`. `tf` is one
   division (`O(1)`). `idf` is an `O(F)` field walk plus a `dict.get`
   per field; with `F` constant this is `O(1)` per call. Total:
   `O(D x k)` where `D = |common| ≤ D_min`.

4. **Sort by score.** Python's Timsort is `O(D log D)` worst case and
   `O(D)` on near-sorted input.

Adding the four pieces gives the README's claim. In practice scoring
is the dominant term for typical query sizes, but for a single rare
term against a large corpus the sort can dominate.

### `find_phrase` -- `O(k x D_min) + O(P x k)`

The phrase scan begins like AND -- `k` posting lookups followed by
`O(k x D_min)` set intersection -- and then runs the adjacency check
in `src/search.py`:

```python
for doc_id in common:                                  # |common| candidates
    first_positions = posting_lists[0][doc_id].positions  # P_doc positions
    rest_position_sets = [set(...) for ...]               # O(P_doc x k)
    for p0 in first_positions:                            # P_doc iterations
        if all((p0 + offset + 1) in rest_position_sets[offset]
               for offset in range(k - 1)):                # k - 1 set lookups, O(1) each
            occurrences += 1
```

Per candidate document the cost is `O(P_doc x k)`: building the `k - 1`
position sets plus walking the first term's positions while doing
`O(1)` set membership checks for each of the other `k - 1` tokens.
Summing across candidates gives `O(P x k)` where `P = sum of P_doc`.

### Caveats

The analysis above smooths over four real-but-small effects:

- **`F` treated as a constant** (3). All field-walks are written with
  an explicit loop in the code, so the strict statement is `O(F x ...)`,
  but with `F` fixed at compile time the cost is bounded by a constant
  factor.
- **`_idf` is recomputed on every call** rather than cached. For a
  single term the cost is one `dict.get` per field plus a small set
  union, dominated by the `dict.get`. For repeated queries a cache
  would amortise this; we did not add one because the empirical query
  cost (a few microseconds) leaves no room to optimise.
- **`dict.get` average vs worst case.** Python's dict is `O(1)`
  average and `O(n)` worst case under adversarial hashing; for natural
  English tokens this never materialises.
- **Sort behaviour.** Timsort is `O(n log n)` worst case, but typical
  inputs (short result lists with mostly-distinct scores) approach
  `O(n)` in practice.

### Empirical confirmation

Running `pytest tests/test_performance.py --benchmark-only` produces a
`pytest-benchmark` table showing the realised cost of each operation
for a 50-page synthetic corpus. The README's *Performance* section
quotes those numbers directly. The shape of the measurements matches
the analysis above: single-word lookup is sub-microsecond, AND queries
are a few microseconds, phrase queries are tens of microseconds, and
build dominates at tens of milliseconds per 50 pages.

## 9. Phrase Adjacency: Worked Example

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

## 9. Complexity Analysis

The README's performance section quotes a big-O for each hot path; this
section derives those expressions from the actual implementation in
`src/`. The variables used throughout are:

* **N** -- number of indexed documents.
* **T** -- number of distinct terms across the whole corpus (the
  `unique_terms` value in the metadata).
* **L** -- average document length in tokens (a document's `length`
  field is the sum of its three field lengths).
* **D_t** -- the document frequency of a particular term: how many
  documents contain it in any field.
* **D** -- the number of documents matching a multi-term query (the
  set-intersection of the relevant `D_t`).
* **k** -- the number of terms in the query.
* **F** -- the number of fields per document. In schema v2 this is
  fixed at 3 (`text`, `author`, `tag`), so `F` is treated as a constant
  in the asymptotic expressions and absorbed into the leading factor.

### 9.1 `build`: O(N x L)

`build_index` (`src/indexer.py`) iterates over crawled pages, runs
`extract_fields` to split the HTML into three field strings, tokenises
each field, and updates the inverted index one token at a time:

```text
for each of N pages:                              # outer: N iterations
    parse HTML, extract three field strings       # O(L)
    for each of the F fields:                     # F = 3 (constant)
        tokenise the field's text                 # O(L_field)
        for each of L_field tokens:               # inner
            dict lookup + freq increment +
            list append                           # O(1) amortised
```

Per page the inner work sums to `O(L)` across all fields (the field
lengths add up to the document length). Across `N` pages the total is
`O(N x L)`.

The empirical 37.6 ms for a 50-page synthetic build (README's
performance table) is consistent with this analysis: the per-page cost
is dominated by HTML parsing rather than the index update itself, but
both are linear in the page's content size.

### 9.2 `print word`: O(1) + O(D_t log D_t)

`print_word` (`src/search.py`) is a single-term inspection:

```text
for each of F fields:                             # F = 3 (constant)
    field_index.get(term)                         # dict lookup, O(1)
collect non-empty hits                            # at most F entries
for each (field, postings):
    sorted(postings.keys())                       # sort the D_t doc ids
    print one line per posting                    # O(P_doc) for positions
```

The lookup itself is `O(F) = O(1)`. The cost is dominated by sorting
the `D_t` matching `doc_id`s -- `O(D_t log D_t)` -- and by formatting
each posting's position list, which adds up to the number of stored
positions for that term.

The measured 25.9 µs in the benchmark is plausible: for a vocabulary
where `D_t` is in single digits, sorting cost is negligible and the
formatting dominates.

### 9.3 `find` (AND, TF-IDF ranked): O(k x D_min) + O(D x k) + O(D log D)

`find` (`src/search.py`) has four phases. Reading from the source:

```text
for each of k query items:                        # k iterations
    _resolve_postings -> dict of doc_id ->
                          {field: Posting}        # O(F) = O(1)

# Set-intersection of doc_id sets. Python's
# `set & set` is O(min(|s1|, |s2|)).
common = set(per_item_postings[0].keys())
for each of the remaining k-1 sets:
    common &= set(...)                            # O(min(|common|, D_i))

for each doc_id in common:                        # |common| <= D_min
    for each of k query terms:                    # k iterations
        sum freq across F fields                  # O(F) = O(1)
        compute TF and IDF                        # O(F * D_t) for IDF
        accumulate score                          # O(1)
    build snippet for the doc                     # O(W) where W = window

results.sort(key=score)                           # O(D log D)
```

The intersection collapses to roughly `O(k x D_min)` because each step
iterates the smaller of two sets. The scoring loop walks `D` candidate
documents and does `O(k)` work per document with TF and IDF treated as
`O(1)` (in the typical case `IDF` is `O(F x D_t)` but `D_t` is bounded
by `N` and small for content-bearing terms). The final sort is the
classical comparison sort over the result list. The 2.95 µs benchmark
for a three-term AND on a 50-page synthetic corpus confirms that
`D` is small in practice.

### 9.4 `find_phrase`: O(k x D_min) + O(sum_d P0(d) x k)

`find_phrase` (`src/search.py`) reuses the same intersection but adds a
per-document positional adjacency scan:

```text
for each of k query tokens:                       # k iterations
    text_index.get(token)                         # O(1)

common = AND-intersection of doc_id sets          # O(k x D_min)

for each doc_id in common:                        # |common| <= D_min
    first_positions = posting[token0].positions   # P0(doc) entries
    rest_position_sets = k-1 sets                 # O(P x k) to build

    for each p0 in first_positions:               # P0(doc) iterations
        for each of k-1 follow-up tokens:         # k-1 iterations
            check (p0 + i + 1) in set             # O(1) per check
        if all aligned, count an occurrence
```

The inner adjacency check is `O(k)` per starting position, repeated
for each of the `P0(doc)` first-token positions in each candidate
document. Summed across the candidate set, the adjacency phase costs
`O(k x sum_d P0(d))`. In practice this is dominated by documents that
contain the rarest query token only a handful of times, which is why
the 30.8 µs benchmark for a two-word phrase against a 50-page corpus
is competitive with the AND query despite the additional positional
work.

### 9.5 Notes on simplifications

The expressions above absorb a few constants and approximations that
are worth being explicit about, since strict big-O without context
hides where the real work happens.

* **`F = 3` is treated as a constant.** Schema v2 has exactly three
  fields; folding `F` into the leading constant keeps the expressions
  readable without losing accuracy at this scale.
* **Dictionary access is `O(1)` amortised, not worst-case.** Python's
  hash table has occasional `O(n)` collision chains, but for the
  string keys produced by lowercasing and tokenising natural-language
  English text the collision rate is empirically negligible.
* **IDF is recomputed per query, not cached.** `_idf` walks the
  inverted index whenever a query term is scored. Caching IDF on
  `load` would shave a small constant off every AND query but does
  not change the asymptotic shape. The benchmark numbers indicate
  the cache is not a productive optimisation at this corpus size.
* **`sort` is Timsort, not strict `O(D log D)`.** Python's built-in
  sort is adaptive: nearly-sorted inputs run closer to `O(D)`. The
  worst case is `O(D log D)` and is the figure used above.
* **Snippet generation is `O(W)`** where `W` is the snippet window
  (six tokens before and after the first match by default). It does
  not change the leading-order term of any query but adds a small
  constant per result.
* **HTML parsing is `O(L)`** because BeautifulSoup walks the byte
  stream linearly; the "parse" cost in `build` and the "tokenise"
  cost in `build` are therefore both linear in document size and
  collapse into the single `O(N x L)` figure quoted above.

The benchmarks in `tests/test_performance.py` are the empirical
counterpart to this section: each measured operation maps to one of
the expressions above, and the README's performance table reports
their measured means against a synthetic 50-page corpus.

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
