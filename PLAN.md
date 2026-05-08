# Search Engine Tool -- Final Plan

> Target site: `https://quotes.toscrape.com/`
> Stack: Python 3.10+, `requests`, `beautifulsoup4`, `pytest`
> Deliverables: GitHub repository and compiled index file.

> **Status note.** The video demonstration and any artefacts that exist
> only to support it (video script, segment-by-segment outline, recording
> workflow) are currently deferred. Phase 7 and Appendix D below are kept
> as a reference for when video work resumes; until then, treat them as
> aspirational rather than active scope. Phases 0-6 are unaffected.

---

## Part I -- Specification

### 1. Overview

A command-line search engine that crawls a small website, builds an inverted
index over the page contents, persists it to disk, and answers single-word,
multi-word, and phrase queries from the index. The tool is invoked as an
interactive shell with four primary commands: `build`, `load`, `print`, `find`.

The system is designed to be:

- **Reproducible** -- running `build` twice on a stable site yields the same index file (modulo `created_at`).
- **Testable** -- every IO boundary (HTTP, sleep, filesystem) is injectable, so the test suite never hits the network and never sleeps for real.
- **Explainable** -- the index file is human-readable JSON; every algorithmic decision has a written rationale.
- **Extensible** -- the posting structure carries enough information (frequencies, positions, length) to support TF-IDF ranking and phrase queries on top of the same data.

### 2. Functional Scope

**In scope**

- Breadth-first crawl of the target site, restricted to the same host.
- Polite crawling with a configurable delay (default 6 seconds).
- Tokenisation of page content (quote text, author, tags) into lowercase word tokens.
- Inverted index keyed by token, storing per-document frequency and positions.
- Persistence to a single JSON file with a schema version and crawl metadata.
- Interactive REPL exposing `build`, `load`, `print`, `find`, plus `help`, `stats`, `exit`.
- AND-semantics multi-word queries.
- TF-IDF ranking of multi-word query results.
- Phrase queries via double-quoted input, evaluated against stored positions.
- Graceful handling of malformed input, missing files, network failures, and unknown words.

**Out of scope**

- Distributed crawling, JavaScript rendering, login-protected pages.
- Stemming, lemmatisation, or language detection.
- Boolean operators beyond implicit AND / phrase.
- Spell correction or query suggestion.
- Persistent caches across builds (a fresh `build` always re-crawls).

### 3. Architecture

The codebase is split into seven cooperating modules under `src/`. Each module
owns one responsibility and exposes a small, typed surface.

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
       |   utils     |   tokenize, safe_request, time injection
       +-------------+
```

- The crawler depends only on `utils` and emits raw `(url, html)` pairs.
- The indexer consumes pages and produces a `SearchIndex` value object.
- The storage module is pure IO -- it serialises and deserialises a `SearchIndex` from JSON.
- The search module is pure computation over a `SearchIndex`; it owns ranking and phrase logic.
- `main.py` wires modules together and contains no business logic of its own.

### 4. Data Model

The on-disk index is a single JSON document with four top-level sections.

```jsonc
{
  "schema_version": 1,
  "metadata": {
    "base_url": "https://quotes.toscrape.com/",
    "created_at": "2026-05-07T12:34:56Z",
    "page_count": 10,
    "total_tokens": 1234,
    "unique_terms": 487,
    "politeness_delay_seconds": 6
  },
  "documents": {
    "doc_001": { "url": "...", "title": "...", "length": 87 }
  },
  "index": {
    "good": {
      "doc_001": { "freq": 2, "positions": [3, 17] }
    }
  }
}
```

Key choices:

- **`schema_version`** lets `load` reject incompatible files with a clear message.
- **`doc_id`** is an internal stable handle; URLs are presentation-only. This keeps the index keys short and lets the document table evolve without rewriting the postings.
- **`positions: list[int]`** preserves order and duplicates. Frequency is stored explicitly to avoid recomputing `len()` on every lookup, but it is always equal to `len(positions)` and is verified by tests as an invariant.
- **`length`** is the total token count of the document, used as the TF denominator.
- **IDF and TF-IDF weights are not persisted** -- they are recomputed on load into an in-memory cache. This keeps the file format minimal and avoids stale weights when the document set changes.

### 5. Module Responsibilities

**`models.py`** -- Pure data classes with type hints. No behaviour beyond `to_dict` / `from_dict` for JSON conversion.

**`utils.py`** -- Tokenisation (`re.findall(r"\b\w+\b", text.lower())`, which is Unicode-aware under Python 3 so non-ASCII letters survive while punctuation -- including curly apostrophes -- splits words at the boundary), HTTP helper with timeout and retry, and a `Clock` abstraction wrapping `time.sleep` so tests can pass a fake clock.

**`crawler.py`** -- Owns the BFS frontier and the seen-set. Accepts `delay_seconds` and a `Clock` in its constructor. Yields `(url, html, title)` tuples lazily so the indexer can stream rather than buffer the whole site. Restricts navigation to the same registered domain. Emits structured log lines for each fetch.

**`indexer.py`** -- Given an iterable of pages, extracts the indexable text from each page, tokenises, and builds a `SearchIndex`. The extraction scope is the page's *semantic content* -- the quote text, author name, and tag list -- and deliberately excludes site chrome (navigation menus, pagination links, footer) so that words appearing on every single page (for example "next", "previous", "login") do not flood the postings and dilute relevance. This is a documented design choice, called out in the README and in `design_notes.md`, not an oversight. The indexer also computes per-document length, total tokens across the corpus, and the unique-term count. Idempotent: indexing the same page set twice produces equal indexes.

**`storage.py`** -- `save(index, path)` and `load(path) -> SearchIndex`. Validates `schema_version` on load. Wraps `json.dump`/`json.load` with explicit UTF-8 encoding and an optional gzip variant. Distinguishes "file missing", "file unreadable", and "schema mismatch" with separate exception types.

**`search.py`** -- Three public functions:

- `print_word(index, word)` -- formatted human-readable output of a single posting list.
- `find(index, terms)` -- AND-intersection across postings, ranked by TF-IDF.
- `find_phrase(index, phrase)` -- AND-intersection followed by a positional scan: a document matches if some position `p` of term[0] is followed by `p+1` of term[1], and so on.

**`main.py`** -- Reads commands in a loop, dispatches to `search` / `storage` / `crawler+indexer`, and prints results. Holds the loaded index in memory between commands. Detects double-quoted phrases and routes them to `find_phrase`.

### 6. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Concurrency | Synchronous `requests` | Site has ~10 pages; politeness window dominates wall-clock time anyway. Async adds risk of multiple in-flight requests violating the 6-second rule. |
| Politeness implementation | Injectable `Clock` + delay | Lets tests verify `sleep` was called with `6` without actually waiting. |
| Position container | `list[int]` | Preserves order, allows duplicates, and is required for phrase queries. A `set` would break both. |
| Index format | JSON | Human-readable, diffable, trivially loadable, no binary tooling required for the marker. Gzip is available as a flag for size-conscious runs. |
| Document key | Synthetic `doc_NNN` | Keeps posting maps small and stable across URL changes. The URL lives once in the document table. |
| Indexable text scope | Quote text + author + tags | Words appearing on every page (navigation, pagination, footer) would dominate the index without informing relevance. The scope is the page's semantic content, surfaced explicitly in the README and `design_notes.md` as a design decision rather than a quiet exclusion. |
| Ranking | TF-IDF, weights computed on load | Pedagogically transparent for the walkthrough; alternatives (BM25) require hyperparameters with no tuning data. Discussed in `design_notes.md`. |
| Stemming | None | Corpus is short literary English; stemming would conflate forms while losing interpretability. |
| CLI parsing | Hand-rolled, plus `shlex` for quoted phrases | No external dependency, behaviour fully visible in source. |

### 7. CLI Contract

The shell prompt is `> `. Commands are case-insensitive at the keyword level; arguments are not. Output is plain text formatted for readability in a terminal recording.

The four **primary commands** are `build`, `load`, `print`, and `find` -- these define the tool's contract and are the focal point of both the README command reference and the recorded demonstration. Everything below those four is **auxiliary** and exists to support inspection, testing, and demonstration; auxiliary commands must never overshadow the primary four in either documentation or video.

*Primary commands.*

| Command | Behaviour |
|---|---|
| `build` | Crawls, builds, saves to `data/index.json`. Prints progress per page (URL fetched, sleep before next request, running document and term counts) and a final summary (page count, total tokens, unique terms, file size, elapsed time). Overwrites any existing file. |
| `load` | Loads `data/index.json` into memory. Reports schema version and metadata. Errors if the file is missing or incompatible. |
| `print <word>` | Shows the posting list for `word`: per-document URL, frequency, and positions. Reports "no matches" cleanly. |
| `find <term...>` | AND-intersects postings. Prints a ranked list of `(rank, url, score, matched-terms)`. Empty query and unknown-word queries print a clear message instead of erroring. |

*Auxiliary commands.*

| Command | Behaviour |
|---|---|
| `find "<phrase>"` | Phrase search using positions. Same output shape as `find`. |
| `stats` | Prints index summary plus the top-20 most frequent tokens. Used to demonstrate Zipf-like distribution. |
| `help` | Lists commands with one-line descriptions. |
| `exit` / `quit` | Leaves the shell cleanly. |

Unknown commands print a help hint and never crash the shell. `print` and `find` issued before `load` print a clear "no index loaded -- run `load` or `build` first" message.

### 8. Testing Strategy

The test suite has four layers, all under `tests/`. Network is always mocked.
Time is always injected. Coverage target is 90%+.

**Unit tests** cover each module in isolation:

- `test_utils.py` -- tokeniser edge cases (empty input, punctuation-only input, mixed case, curly apostrophe splitting `don't` into `don` and `t`, a non-ASCII letter preserved as a token so the Unicode policy is locked down), clock injection.
- `test_crawler.py` -- frontier expansion, same-host restriction, sleep invocation count and argument, retry on transient failure, abort on persistent failure.
- `test_indexer.py` -- frequency / position correctness on hand-crafted HTML, document length, idempotence, scope restriction (navigation text excluded).
- `test_storage.py` -- round-trip equality, schema-version mismatch, missing file, malformed JSON.
- `test_search.py` -- single-word lookup, AND intersection, TF-IDF ordering on a synthetic three-document corpus where the expected ranking is computable by hand, phrase matching including a negative case where the words exist but not adjacent.

**Integration tests** in `test_integration.py` wire crawler -> indexer -> storage -> search end-to-end against an in-memory mock site (a dict of `url -> html`). Verifies the four CLI commands as a sequence.

**CLI tests** in `test_cli.py` drive `main.py` with scripted stdin and assert on stdout. Covers unknown commands, `find` before `load`, empty queries, and clean exit.

**Performance tests** in `test_performance.py` use `pytest-benchmark` to record:

- `build` end-to-end against the mock site
- single-word lookup
- 3-word AND intersection
- phrase query
- TF-IDF top-10 ranking

Results are committed and reproduced in `README.md`'s performance table.

**Quality gates** (enforced in CI, see Appendix C):

- `ruff check` -- style
- `mypy src` -- types (default strictness; BeautifulSoup and JSON dataclass conversion produce too much noise under `--strict` for the value gained on a project this size)
- `pytest --cov=src --cov-fail-under=85` -- the README aspirational target is 90%, but the CI gate is set at 85% so a single flaky measurement does not block a merge

### 9. Documentation Deliverables

- **`README.md`** -- Project overview, install, quickstart, command reference, architecture diagram, index schema, performance table, design summary, GenAI declaration, license, badges (CI, coverage, Python version).
- **`docs/design_notes.md`** -- Algorithmic rationale and references: inverted index layout (Manning et al., *Introduction to Information Retrieval*), ranking choice (TF-IDF vs BM25), tokenisation choice (no stemming, with reasoning), Zipf validation linked to the `stats` command.
- *(Deferred)* A timed video script lived at `docs/video_script.md`; it has been removed while video work is on hold. Appendix D below preserves the segment-level outline for when recording resumes.

### 10. Optional Extensions

Three features may extend the core system once the v1 baseline is stable.
They are **optional**: the project ships and is internally coherent without
them. They share a common thesis: the data structures already in place can
do more than the four required commands, and exposing that extra capability
makes the project read more like a small search engine and less like a
homework exercise. They live in a dedicated late phase (Phase 6) so the
core remains shippable on its own, and each can be adopted independently
or skipped.

**Fielded search.** The corpus naturally has three fields per document:
quote text, author, and tag list. The extended index keeps a separate
posting list per field, all sharing the same `doc_id` space. The CLI
accepts `field:term` tokens in queries, so `find love author:wilde` returns
quotes containing *love* whose author is Wilde. Unprefixed terms search
across all fields, preserving backward-compatible behaviour.

**Match snippets with highlighting.** When extensions are enabled, the
document table additionally stores the original token sequence for each
document. `find` then prints a windowed excerpt around the first match for
each result, with matched terms wrapped in brackets. This turns the result
output from a list of URLs into something closer to a real search-engine
result page, and it is the second use of the position data already
required by the core spec.

**Score explanation mode.** A `--explain` flag on `find` prints the per-term
TF-IDF breakdown -- `tf`, `idf`, their product, and the final document
score -- for every result. The flag does not change ranking; it only exposes
the arithmetic. This makes the ranking behaviour auditable from the shell
and serves as a live demonstration that the implementation matches the
formula in `design_notes.md`.

**Schema impact.** Enabling extensions bumps the on-disk schema to version
2: postings are nested under field names, and each document carries
per-field token streams. The version check in `storage.load` rejects v1
files explicitly with a "rebuild required" message rather than carrying
silent migration code; this is documented as a deliberate simplicity-
over-compatibility choice in `docs/design_notes.md` section 7.

---

## Part II -- Execution Playbook

Each phase has a single clear goal, a branch, a set of files touched, an
explicit definition of done, and a tag at completion when applicable.

### Phase 0 -- Scaffolding

**Goal.** Create the empty skeleton of the project so every later commit lands in the right place.

**Branch.** `main` (initial commit).

**Files created.**

- `src/__init__.py`, empty stubs for `models.py`, `crawler.py`, `indexer.py`, `storage.py`, `search.py`, `utils.py`, `main.py`.
- `tests/` with empty stubs matching each module.
- `data/.gitkeep`.
- `docs/design_notes.md` (outline).
- `requirements.txt` (`requests`, `beautifulsoup4`), `requirements-dev.txt` (`pytest`, `pytest-cov`, `pytest-benchmark`, `ruff`, `mypy`, `responses`).
- `.gitignore`, `pyproject.toml` (ruff + mypy config), `.github/workflows/ci.yml`.
- `README.md` skeleton with section headings filled in.

**Definition of done.**

- Repository pushes to GitHub.
- CI runs and passes (empty test suite + lint).
- README renders on GitHub with placeholder badges.

**Tag.** `v0.1-scaffold`.

### Phase 1 -- Crawler

**Goal.** Reliable BFS crawl of the target site with injectable politeness.

**Branch.** `feat/crawler`.

**Files.** `src/utils.py` (Clock, safe_request), `src/crawler.py`, `tests/test_utils.py`, `tests/test_crawler.py`.

**Work.**

1. Implement `Clock` and `safe_request` in `utils.py`.
2. Implement `Crawler` accepting `start_url`, `delay_seconds`, `clock`, `http`. Same-host filter using `urllib.parse`. Frontier as `deque`, seen-set as `set`. Yields `(url, html, title)`.
3. Tests with `responses` library: 3-page mock site verifies all pages discovered, `clock.sleep` called exactly twice with `6`, retry-then-succeed, retry-then-fail, off-host link skipped.

**Definition of done.** Crawler runs end-to-end against the live site once as a manual smoke test; unit tests green; coverage on `crawler.py` >= 95%.

### Phase 2 -- Indexer

**Goal.** Produce a correct `SearchIndex` from a stream of pages.

**Branch.** `feat/indexer`.

**Files.** `src/models.py`, `src/indexer.py`, `tests/test_indexer.py`.

**Work.**

1. Define `Document`, `Posting`, `SearchIndex` dataclasses with type hints and `to_dict` / `from_dict`.
2. Implement `extract_text(html)` returning quote text + author + tags concatenated, deliberately excluding nav and pagination.
3. Implement `build_index(pages, base_url)` producing a `SearchIndex` with metadata.
4. Tests: hand-crafted HTML with known quotes, exact frequency and position assertions, idempotence test, scope test (navigation words must not appear in the index), Unicode and punctuation handling.

**Definition of done.** Indexer composed with crawler (manual run) produces a sane index.json; unit tests green; coverage >= 95%.

### Phase 3 -- Storage and CLI shell

**Goal.** Make the system usable end-to-end.

**Branch.** `feat/storage-cli`.

**Files.** `src/storage.py`, `src/main.py`, `tests/test_storage.py`, `tests/test_cli.py`.

**Work.**

1. `storage.save / load` with schema-version check and typed exceptions.
2. REPL in `main.py`: command dispatch, error messages, no-index-loaded guard.
3. Implement `print` (basic posting list view) and a minimal `find` (AND only, no ranking yet -- ranking comes in Phase 4).
4. Tests: round-trip, version mismatch, missing file, scripted REPL covering all four commands and error paths.

**Definition of done.** `python -m src.main` opens a shell, `build` then `print indifference` then `find good friends` all work against the live site.

**Tag.** `v0.5-mvp`.

### Phase 4 -- Search ranking and phrase queries

**Goal.** TF-IDF ranking and phrase support without changing the on-disk format.

**Branch.** `feat/search-ranking`.

**Files.** `src/search.py`, `tests/test_search.py` (expanded).

**Work.**

1. On `load`, build an in-memory IDF table.
2. `find` returns ranked results with score and matched-terms breakdown.
3. CLI parser uses `shlex` to detect double-quoted phrases and routes to `find_phrase`.
4. `find_phrase` algorithm: take the AND intersection, then for each candidate document, scan for `p, p+1, p+2, ...` chains across the term position lists.
5. Tests: a synthetic three-document corpus where TF-IDF ordering is computed by hand and asserted; phrase positive case; phrase negative case (words present but not adjacent); empty query; single-quoted vs double-quoted; case-insensitive phrase.

**Definition of done.** Ranking visible in `find` output. Phrase query distinguishes adjacent from non-adjacent occurrences.

### Phase 5 -- Tests, benchmarks, documentation

**Goal.** Lift coverage to >=90%, add benchmarks, finalise written docs.

**Branch.** `feat/quality`.

**Files.** `tests/test_integration.py`, `tests/test_performance.py`, `README.md`, `docs/design_notes.md`.

**Work.**

1. Integration test wiring all modules against an in-memory mock site.
2. Benchmark suite with five measurements (build, lookup, AND, phrase, rank).
3. Add a `stats` command that prints the top-20 tokens; add a Zipf observation to `design_notes.md`.
4. Finalise `README.md`: architecture diagram, install, quickstart, full command reference, schema reference, performance table, design summary, GenAI declaration, references.
5. Finalise `design_notes.md`: inverted index layout, ranking choice, tokenisation choice, Zipf validation, references to Manning IR, BM25 paper, Porter (1980).
6. *(Deferred until video work resumes.)* Draft the GenAI reflection talking points -- two concrete moments from Phases 1-5 plus a one-sentence learning implication -- in whatever artefact replaces `docs/video_script.md`.

**Definition of done.** CI green at coverage >= 90%. README and `design_notes.md` complete; `stats` command works.

**Tag.** `v0.9-rc`.

### Phase 6 -- Optional Extensions

**Status.** Optional. This phase is entered only after `v0.9-rc` is fully
green: tests, coverage, README, and design notes all complete.
If time, energy, or stability budget is tight, **skip this phase entirely**
and ship `v0.9-rc` as `v1.0`. The shippable product is the core plus
TF-IDF ranking, phrase queries, and the `stats` command -- nothing in
Phase 6 is required to make the project coherent on its own.

The features in this phase are also independent of each other and can be
adopted one at a time. A reasonable fallback ordering is: do `--explain`
first (cheapest, biggest demo payoff, no schema change), then snippets
(needs `tokens` field but no posting reshape), then fielded search
(largest change, requires schema v2). Stop at the first feature where
stability looks at risk.

**Goal.** Layer fielded search, match snippets, and a score-explanation
mode on top of a stable, fully tested v1 core. If any extension proves
unstable, revert it without affecting the shippable v1.

**Branch.** `feat/extensions`.

**Files touched.** `src/models.py` (schema v2 dataclasses), `src/indexer.py`
(field-aware extraction + token retention), `src/storage.py` (version-aware
load), `src/search.py` (field-prefixed queries, snippet generation,
explanation breakdown), `src/main.py` (CLI parser updates for `field:term`
and `--explain`), and the corresponding test files.

**Work.**

1. Bump `schema_version` to 2. Update `models.py` so `SearchIndex.index`
   becomes `dict[field, dict[term, dict[doc_id, Posting]]]` and `Document`
   gains a `tokens: list[str]` array. Keep v1 readable by branching on the
   loaded version inside `storage.load`.
2. Refactor `indexer.build_index` to emit one posting list per field
   (`text`, `author`, `tag`) while sharing `doc_id` and `length`. Retain
   the raw token sequence for each document so snippets can be assembled
   later without re-parsing HTML.
3. Extend the CLI parser to recognise `field:term` tokens. Unprefixed
   terms fan out across all fields and union their postings before AND
   intersection. The phrase-query path continues to operate on the `text`
   field only.
4. Implement `make_snippet(tokens, match_positions, window)` returning a
   short context string with matched terms wrapped in brackets. Wire it
   into the `find` output formatter.
5. Add a `--explain` flag handled in `main.py` and threaded through
   `search.find`. When set, the formatter prints the `tf`, `idf`,
   `tf*idf`, and per-document totals for every term in the query.
6. Update `tests/test_search.py` and `tests/test_storage.py` to cover:
   field-prefixed queries; cross-field default behaviour; snippet
   correctness on hand-crafted token sequences; `--explain` arithmetic
   verified against hand-computed values; v1 file rejected with a clear
   "rebuild required" message under v2 code.
7. Update `README.md`'s command reference and schema section, and add a
   short "Extensions" subsection in `docs/design_notes.md` explaining how
   each extension reuses existing data rather than duplicating it.

**Definition of done.** All of the following work in a fresh shell:

- `find love author:wilde` returns Wilde quotes containing *love*.
- `find friends` prints results with bracketed snippets around the match.
- `find --explain good friends` prints a per-term TF-IDF breakdown whose
  numbers match the values in `design_notes.md`.
- A v1 index file from the `v0.9-rc` tag is rejected by `load` with a clear "schema v1 ... run 'build' to regenerate" message, and a fresh `build` produces a v2 file that loads cleanly.
- CI remains green at coverage >= 90%.

**Tag.** `v0.95-extensions`.

### Phase 7 -- Video and submission

**Goal.** Produce the recorded demonstration and the final submission bundle.

**Branch.** `release/v1.0`.

**Work.**

1. Run `build` once against the live site to produce the final `data/index.json`. Commit it. This is the file that ships with the submission. A second `build` run is performed on camera during the recording (see Appendix D); the on-disk artefact from the first off-camera run is the one attached to the Minerva submission.
2. Follow `docs/video_script.md` to record a 5-minute screen capture (see Appendix D for the per-segment outline). All four primary commands are demonstrated live; `build` runs on camera for two or three pages and is then continued through a single video cut so the demo budget is preserved.
3. Upload the video to a shared link and verify it opens in an incognito window.
4. Tag `v1.0`, draft a GitHub Release with the index file attached.
5. Prepare the Minerva submission document: video URL + repository URL + index file attachment.

**Definition of done.** Tag `v1.0` exists, release is published, video link verified, submission document prepared.

---

## Part III -- Appendix

### A. Final directory tree

```
Search-Engine-Tool/
+-- .github/
|   +-- workflows/
|       +-- ci.yml
+-- src/
|   +-- __init__.py
|   +-- crawler.py
|   +-- indexer.py
|   +-- main.py
|   +-- models.py
|   +-- search.py
|   +-- storage.py
|   +-- utils.py
+-- tests/
|   +-- __init__.py
|   +-- test_cli.py
|   +-- test_crawler.py
|   +-- test_indexer.py
|   +-- test_integration.py
|   +-- test_performance.py
|   +-- test_search.py
|   +-- test_storage.py
|   +-- test_utils.py
+-- data/
|   +-- index.json
+-- docs/
|   +-- design_notes.md
+-- .gitignore
+-- pyproject.toml
+-- requirements.txt
+-- requirements-dev.txt
+-- README.md
```

### B. Dependencies

`requirements.txt`

```
requests>=2.31
beautifulsoup4>=4.12
```

`requirements-dev.txt`

```
pytest>=8.0
pytest-cov>=5.0
pytest-benchmark>=4.0
responses>=0.25
ruff>=0.4
mypy>=1.10
```

### C. Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, across Python
3.10, 3.11, and 3.12. Steps: checkout, setup Python, install requirements,
`ruff check`, `mypy src`, `pytest --cov=src --cov-fail-under=85`, upload
coverage. The repository displays badges for CI status, coverage, and Python
version at the top of the README.

### D. Video script outline (5:00 hard cap)

| Time | Segment | Content |
|---|---|---|
| 0:00-2:00 | Live demonstration | Run all four primary commands on camera. Start with `build`: let it run live for the first two or three pages so the audience sees real fetches, the 6-second sleep between requests, and the running progress output; then use a single visible video cut (with an on-screen caption such as "build continued -- full crawl takes ~60 seconds") to skip to the build summary line, so the demo budget is not consumed by waiting. Then `load` to confirm the index round-trips from disk; `print indifference` to show a single-word posting list with frequency and positions; `find good friends` to show multi-word AND with ranking. Close with one edge case (unknown word or empty query). If extensions shipped, demonstrate **at most one** auxiliary capability -- `find --explain good friends` is the recommended choice because it reads fast on screen and reinforces the ranking discussion. The auxiliary demo, if shown, must clearly come after the four primary commands, not interleaved with them. |
| 2:00-3:30 | Code walkthrough | Open `models.py` and explain the schema; open `indexer.py` for tokenisation and the deliberately narrow extraction scope; open `search.py` for AND intersection, TF-IDF, and the phrase scan over positions; name the key trade-offs (list vs set for positions, JSON vs binary, sync vs async, TF-IDF vs BM25). Mention extensions only if they shipped and only briefly. |
| 3:30-4:00 | Tests and CI | `pytest --cov` locally, coverage number on screen; highlight the test that asserts the crawler called `clock.sleep(6)` the expected number of times -- this is the deterministic evidence backing the live `build` segment, where only the first sleeps were visible on camera. Switch to GitHub Actions tab showing the matrix of green runs; one `pytest-benchmark` table. |
| 4:00-4:30 | Git workflow | `git log --oneline --graph --all` showing feature branches merging into `main`; `git tag` listing v0.1 / v0.5 / v0.9 / v0.95 / v1.0; one release page screenshot. |
| 4:30-5:00 | GenAI reflection | Two concrete episodes from the development process -- one where AI helped, one where it misled or required correction -- and one sentence on the broader implication for learning. Talking points are prepared in `docs/video_script.md`; there is no separate log file. |

### E. Commit and branch conventions

- **Commit prefix.** `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `ci:`, `chore:`. Subject <= 72 characters, imperative mood.
- **Branches.** `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `release/<version>`. Merged into `main` with `--no-ff` to preserve the merge node in the history graph.
- **Tags.** `v0.1-scaffold`, `v0.5-mvp`, `v0.9-rc`, `v0.95-extensions`, `v1.0`. Each tag corresponds to a phase's definition of done.

### F. Open decisions

None. All choices listed in section 6 are committed for v1.0. Any change after Phase 4
requires a written entry in `design_notes.md` explaining the reason.
