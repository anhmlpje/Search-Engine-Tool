"""Placeholder benchmark tests. Real benchmarks land in Phase 5."""

from src import indexer, search


def test_modules_load() -> None:
    for module in (indexer, search):
        assert module.__doc__ is not None
