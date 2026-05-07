"""Inverted-index serialisation and deserialisation as JSON files.

The on-disk format is human-readable JSON with an embedded ``schema_version``
so that an incompatible file can be rejected with a clear error rather than
silently misinterpreted. The three failure modes -- file missing, file
unreadable, file from a different schema version -- are surfaced as
distinct exception types so the CLI layer can word each error appropriately.
"""

import json
from pathlib import Path

from src.models import SCHEMA_VERSION, SearchIndex


class IndexFileError(Exception):
    """Base class for all storage-layer failures."""


class IndexNotFound(IndexFileError):
    """Raised when the requested index file does not exist on disk."""


class IndexCorrupt(IndexFileError):
    """Raised when the file exists but cannot be parsed as JSON."""


class SchemaMismatch(IndexFileError):
    """Raised when the file's ``schema_version`` is not supported."""


def save(index: SearchIndex, path: Path | str) -> None:
    """Serialise ``index`` to UTF-8 JSON at ``path``, creating parent dirs."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(index.to_dict(), fh, ensure_ascii=False, indent=2)


def load(path: Path | str) -> SearchIndex:
    """Read an index from ``path``, validating the embedded schema version."""
    target = Path(path)
    if not target.exists():
        raise IndexNotFound(f"index file not found: {target}")
    try:
        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise IndexCorrupt(f"index file is not valid JSON: {target}: {exc}") from exc

    if not isinstance(data, dict):
        raise IndexCorrupt(f"index file is not a JSON object: {target}")

    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        if version == 1:
            raise SchemaMismatch(
                f"index file at {target} uses schema v1; "
                f"current code requires v{SCHEMA_VERSION} "
                f"(field-aware index with per-document token streams). "
                "Run 'build' to regenerate the index file."
            )
        raise SchemaMismatch(
            f"schema version mismatch in {target}: "
            f"expected {SCHEMA_VERSION}, got {version!r}"
        )

    return SearchIndex.from_dict(data)
