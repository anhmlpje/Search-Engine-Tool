# Search Engine Tool

[![CI](https://github.com/anhmlpje/Search-Engine-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/anhmlpje/Search-Engine-Tool/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/anhmlpje/Search-Engine-Tool/branch/main/graph/badge.svg)](https://codecov.io/gh/anhmlpje/Search-Engine-Tool)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

> Status: scaffolding (v0.1). See [PLAN.md](PLAN.md) for the full execution plan.

An inverted-index search engine over [quotes.toscrape.com](https://quotes.toscrape.com/),
exposed as an interactive command-line shell with four primary commands:
`build`, `load`, `print`, and `find`.

## Features

*To be filled in as phases land.*

- Polite breadth-first crawl with a configurable delay (default 6 seconds).
- Inverted index storing per-document frequency and word positions.
- Single-file JSON persistence with a schema version.
- Multi-word AND queries ranked by TF-IDF.
- Phrase queries via double-quoted input.

## Installation

```bash
python -m venv .venv
. .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For development:

```bash
pip install -r requirements-dev.txt
```

## Quickstart

*To be filled in once the CLI lands in Phase 3.*

```text
$ python -m src.main
> build
> load
> print indifference
> find good friends
> exit
```

## Commands

### Primary

| Command          | Description                                                  |
|------------------|--------------------------------------------------------------|
| `build`          | Crawl the target site and build the inverted index.          |
| `load`           | Load a previously built index from disk.                     |
| `print <word>`   | Show the posting list for a word.                            |
| `find <terms>`   | Return pages containing all terms, ranked by relevance.      |

### Auxiliary

| Command              | Description                                              |
|----------------------|----------------------------------------------------------|
| `find "<phrase>"`    | Phrase search using stored positions.                    |
| `stats`              | Index summary plus the top-20 most frequent tokens.      |
| `help`               | List commands.                                           |
| `exit` / `quit`      | Leave the shell.                                         |

## Architecture

*Diagram and module overview to be added in Phase 5. See [PLAN.md](PLAN.md)
section 3 for the current architecture sketch.*

## Index schema

*Reference to be added in Phase 2 once the schema is implemented. See
[PLAN.md](PLAN.md) section 4 for the design.*

## Testing

```bash
pytest --cov=src --cov-report=term-missing
```

The CI pipeline runs `ruff`, `mypy`, and `pytest` with a coverage gate on
every push and pull request across Python 3.10, 3.11, and 3.12.

## Performance

*Benchmark table to be added in Phase 5.*

## Design

See [docs/design_notes.md](docs/design_notes.md) for the algorithmic
rationale and references.

## GenAI declaration

This project was developed with assistance from a generative AI tool,
discussed and reflected on in the recorded video demonstration.

## License

*To be added.*
