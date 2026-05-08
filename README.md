# Search Engine Tool

[![CI](https://github.com/anhmlpje/Search-Engine-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/anhmlpje/Search-Engine-Tool/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

An inverted-index search engine over [quotes.toscrape.com](https://quotes.toscrape.com/),
exposed as an interactive command-line shell. Crawls the site politely,
builds a positional inverted index over the page contents, and answers
single-word, multi-word AND, and phrase queries with TF-IDF ranking.

## Highlights

- Polite breadth-first crawl with a configurable delay (default 6 seconds), respected on retries as well as between successful requests.
- Inverted index storing per-document term frequency and the ordered list of in-document positions, all behind a typed dataclass model.
- Single-file JSON persistence with a `schema_version` that `load` validates before parsing.
- Multi-word queries ranked by classical TF-IDF; quoted-phrase queries evaluated as a positional adjacency scan over the same posting data.
- Interactive REPL with the four primary commands the brief requires (`build`, `load`, `print`, `find`) plus auxiliary commands for inspection (`stats`, `help`).
- Quality gates run on every push: `ruff` lint, `mypy` types, `pytest` with a coverage floor of 85% across Python 3.10, 3.11, and 3.12.

## Installation

The project targets Python 3.10 or newer. Set up a virtual environment
and install the runtime dependencies:

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For development (tests, linting, type-checking, benchmarks):

```bash
pip install -r requirements-dev.txt
```

## Quickstart

Run the shell from the project root:

```bash
python -m src.main
```

A typical session:

```text
Search Engine Tool. Type help or ? to list commands.
> build
[build] crawling https://quotes.toscrape.com/
[fetch] https://quotes.toscrape.com/
[fetch] https://quotes.toscrape.com/login
... (the full crawl honours the 6-second politeness window)
[built] pages=214 tokens=29918 terms=4503
[saved] data/index.json
> load
[loaded] pages=214 tokens=29918 terms=4503
> print indifference
word: indifference
documents: 11
  doc_011  https://quotes.toscrape.com/tag/inspirational/page/1/  freq=5  positions=[307, 317, 327, 338, 344]
  ...
> find good friends
1. https://quotes.toscrape.com/tag/books/page/1/  tfidf=0.0123  matched=[good=3 friends=2]
2. https://quotes.toscrape.com/tag/books/         tfidf=0.0123  matched=[good=3 friends=2]
...
> find "good friends"
1. https://quotes.toscrape.com/tag/books/page/1/  occurrences=1  matched=[good=3 friends=2]
> stats
[stats] pages=214 tokens=29918 terms=4503
top 20 tokens by total corpus frequency:
   1. the                  1243
   2. of                   778
   3. and                  765
   ...
> exit
```

## Commands

The shell reads commands at the `> ` prompt. Command keywords are
case-insensitive; arguments are not. The shell never crashes on unknown
commands, malformed input, or `Ctrl+C`.

### Primary

| Command            | Description                                                                                                                   |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `build`            | Crawl the target site, build the inverted index, and save it to `data/index.json`. Overwrites any existing file.              |
| `load`             | Load a previously built index from `data/index.json` into memory. Errors if the file is missing or has an unknown schema.     |
| `print <word>`     | Show the posting list for `word`: per-document URL, frequency, and positions. Reports "no matches" cleanly.                   |
| `find <terms>`     | AND-intersect postings, ranked by TF-IDF. Empty queries and unknown words print a clear message instead of erroring.          |

### Auxiliary

| Command                  | Description                                                                                                       |
|--------------------------|-------------------------------------------------------------------------------------------------------------------|
| `find "<phrase>"`        | Phrase search: text-field documents matched only when the tokens of the phrase appear at consecutive positions.   |
| `find <field>:<term>`    | Fielded search: restrict a term to a specific field (`text`, `author`, or `tag`). Mix with bare terms freely.     |
| `find --explain <terms>` | Show the per-term TF-IDF arithmetic (`freq`, `tf`, `idf`, `tfidf`) for every matched document; default off.       |
| `stats`                  | Index summary plus the 20 most frequent tokens; useful for sanity-checking the tokenisation distribution.         |
| `help`                   | List commands with one-line descriptions.                                                                         |
| `exit` / `quit`          | Leave the shell.                                                                                                  |

Query input is run through the same tokeniser the index was built with,
so `find good!` matches the indexed word `good`, and `find "good friends"`
finds the phrase even if the user writes it with smart quotes. `find`
results carry a short context snippet drawn from the document's stored
text tokens, with matched terms wrapped in brackets:

```text
1. https://...quote-page/  tfidf=0.0349  matched=[good=2 friends=1]
   ...the world is full of [GOOD] [FRIENDS] who...
```

The example below shows fielded queries:

```text
> find author:wilde
1. https://quotes.toscrape.com/author/Oscar-Wilde  tfidf=...  matched=[author:wilde=1]

> find love author:wilde
1. https://quotes.toscrape.com/...  tfidf=...  matched=[love=2 author:wilde=1]
```

## Architecture

```
                  +-------------+
                  |   main.py   |   REPL: parses commands, prints output
                  +------+------+
                         |
              +----------+----------+
              |                     |
       +------v------+       +------v------+
       |  crawler    |       |   search    |
       +------+------+       +------+------+
              |                     |
       +------v------+       +------v------+
       |  indexer    |<------+  storage    |
       +------+------+       +-------------+
              |
       +------v------+
       |   models    |   dataclasses: Document, Posting, SearchIndex
       +-------------+

       +-------------+
       |   utils     |   tokenize, safe_request, Clock injection
       +-------------+
```

Each `src/` module has a single responsibility and a small, typed
surface. `models` is pure data; `utils` owns IO primitives that need
mocking; `crawler` and `indexer` are the producers; `storage` handles
JSON; `search` is pure computation; `main` is the only place that
imports anything other than the internal API.

## Index file schema

The on-disk format is a single UTF-8 JSON document. The `schema_version`
field is checked by `load` and an incompatible file is rejected with a
distinct exception type before any parsing of the inner structure.

```jsonc
{
  "schema_version": 1,
  "metadata": {
    "base_url": "https://quotes.toscrape.com/",
    "created_at": "2026-05-07T12:34:56Z",
    "page_count": 214,
    "total_tokens": 29918,
    "unique_terms": 4503,
    "politeness_delay_seconds": 6.0
  },
  "documents": {
    "doc_001": { "url": "https://...", "title": "...", "length": 87 }
  },
  "index": {
    "good": {
      "doc_001": { "freq": 2, "positions": [3, 17] }
    }
  }
}
```

`Posting.freq` is always equal to `len(Posting.positions)`; the test
suite enforces this invariant across every term in a built index.

## Performance

Measured with `pytest tests/test_performance.py --benchmark-only` on
the project conda environment (Python 3.11, Windows, against a
synthetic 50-page in-memory corpus):

| Operation                              | Mean     | Notes                                                          |
|----------------------------------------|----------|----------------------------------------------------------------|
| Single-word lookup                     | 0.108 us | dictionary access on the term map                              |
| `print word` formatter                 | 29.4 us  | sort by `doc_id` and format posting list across three fields   |
| `find` 3-term AND with TF-IDF ranking  | 14.6 us  | per-field posting lookup, intersection, scoring, rank, snippet |
| `find "phrase"` two-word phrase scan   | 48.9 us  | adjacency check over text positions plus snippet assembly      |
| `build` 50 pages                       | 37.6 ms  | parse HTML, extract three fields, tokenise, accumulate         |

Complexity, in big-O terms over `N` documents, `T` unique terms, and
`L` average document length:

- `build` is `O(N x L)` for scanning, with an `O(L)` posting append per token.
- Single-term lookup is `O(1)` (dict.get) plus `O(D log D)` to sort by `doc_id`, where `D` is the number of matching documents.
- AND with `k` query terms is `O(k x D_min)` for the smallest posting set, then `O(D x k)` for scoring, then `O(D log D)` to rank.
- Phrase search is bounded by the number of positions of the rarest query term in the candidate documents.

## Testing

The full test matrix lives under `tests/`:

```bash
pytest                                   # all unit + integration + benchmarks
pytest --cov=src --cov-report=term-missing
pytest tests/test_performance.py --benchmark-only
ruff check src tests
mypy src
```

CI runs the same chain on every push and pull request across Python
3.10, 3.11, and 3.12 with an 85% coverage floor.

## Design

The algorithmic and structural choices behind the implementation are
written up in [docs/design_notes.md](docs/design_notes.md), with
references to Manning et al.'s *Introduction to Information Retrieval*,
Robertson and Zaragoza's BM25 framework, and Zipf's law as an empirical
baseline.

## Manual smoke

`scripts/smoke_crawler.py` performs a partial real-network crawl of
`quotes.toscrape.com` (only the first three reachable pages, so the
politeness budget stays small) to confirm that the crawler works
end-to-end against live HTML. It is not run in CI; invoke it manually
when validating against the real site:

```bash
PYTHONPATH=. python scripts/smoke_crawler.py
```

## GenAI declaration

This project was developed with assistance from a generative AI tool.

## References

See [docs/design_notes.md](docs/design_notes.md) for a numbered
references list, including:

- Manning, Raghavan, and Schuetze, *Introduction to Information Retrieval*, Cambridge University Press, 2008.
- Porter, "An Algorithm for Suffix Stripping", *Program* 14(3), 1980.
- Robertson and Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*, FnTIR 3(4), 2009.
- Zipf, *Human Behavior and the Principle of Least Effort*, Addison-Wesley, 1949.
