"""Tests for src.storage."""

import json
from pathlib import Path

import pytest

from src.models import (
    Document,
    IndexMetadata,
    Posting,
    SearchIndex,
)
from src.storage import (
    IndexCorrupt,
    IndexNotFound,
    SchemaMismatch,
    load,
    save,
)


def _tiny_index() -> SearchIndex:
    return SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=1,
            total_tokens=2,
            unique_terms=2,
            politeness_delay_seconds=6.0,
        ),
        documents={"doc_001": Document(url="https://x/", title="X", length=2)},
        index={
            "hello": {"doc_001": Posting(freq=1, positions=[0])},
            "world": {"doc_001": Posting(freq=1, positions=[1])},
        },
    )


class TestSave:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "deeply" / "nested" / "idx.json"
        save(_tiny_index(), path)
        assert path.exists()

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.json"
        save(_tiny_index(), path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["schema_version"] == 1
        assert "metadata" in data
        assert "documents" in data
        assert "index" in data


class TestLoad:
    def test_round_trip_equality(self, tmp_path: Path) -> None:
        original = _tiny_index()
        path = tmp_path / "idx.json"
        save(original, path)
        loaded = load(path)
        assert loaded == original

    def test_missing_file_raises_index_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(IndexNotFound):
            load(tmp_path / "missing.json")

    def test_malformed_json_raises_index_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(IndexCorrupt):
            load(path)

    def test_top_level_array_raises_index_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(IndexCorrupt):
            load(path)

    def test_higher_schema_version_raises_mismatch(self, tmp_path: Path) -> None:
        path = tmp_path / "v999.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 999,
                    "metadata": {},
                    "documents": {},
                    "index": {},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(SchemaMismatch):
            load(path)

    def test_missing_schema_version_raises_mismatch(self, tmp_path: Path) -> None:
        path = tmp_path / "noversion.json"
        path.write_text(
            json.dumps({"metadata": {}, "documents": {}, "index": {}}),
            encoding="utf-8",
        )
        with pytest.raises(SchemaMismatch):
            load(path)
