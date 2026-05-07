"""Placeholder integration tests wiring crawler + indexer + storage + search.

Real tests land in Phase 5.
"""

from src import crawler, indexer, search, storage


def test_modules_load() -> None:
    for module in (crawler, indexer, storage, search):
        assert module.__doc__ is not None
