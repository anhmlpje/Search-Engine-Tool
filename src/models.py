"""Data classes for documents, postings, metadata, and the search index.

Schema version 2 introduces *fielded* indexing: each document carries
multiple per-field token streams (text, author, tag), and the inverted
index nests by field. This lets the CLI route ``field:term`` queries to
a specific field's posting list and lets the search layer build context
snippets from the document's stored token stream without re-parsing HTML.
"""

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 2


@dataclass
class FieldData:
    """A single document's content in one indexable field."""

    length: int  # token count for this field
    tokens: list[str]  # raw lowercase tokens, used for snippet generation

    def to_dict(self) -> dict[str, Any]:
        return {"length": self.length, "tokens": list(self.tokens)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldData":
        return cls(length=int(data["length"]), tokens=list(data["tokens"]))


@dataclass
class Document:
    """A single crawled page registered in the index."""

    url: str
    title: str
    length: int  # total token count across all fields
    fields: dict[str, FieldData]

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "length": self.length,
            "fields": {name: fd.to_dict() for name, fd in self.fields.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        return cls(
            url=data["url"],
            title=data["title"],
            length=int(data["length"]),
            fields={
                name: FieldData.from_dict(fd_data)
                for name, fd_data in data["fields"].items()
            },
        )


@dataclass
class Posting:
    """A single ``(term, document)`` entry in a field's inverted index."""

    freq: int
    positions: list[int]  # token offsets within the field's token stream

    def to_dict(self) -> dict[str, Any]:
        return {"freq": self.freq, "positions": list(self.positions)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Posting":
        return cls(freq=int(data["freq"]), positions=list(data["positions"]))


@dataclass
class IndexMetadata:
    """Top-level index summary for the on-disk JSON file."""

    base_url: str
    created_at: str
    page_count: int
    total_tokens: int
    unique_terms: int
    politeness_delay_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "created_at": self.created_at,
            "page_count": self.page_count,
            "total_tokens": self.total_tokens,
            "unique_terms": self.unique_terms,
            "politeness_delay_seconds": self.politeness_delay_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexMetadata":
        return cls(
            base_url=data["base_url"],
            created_at=data["created_at"],
            page_count=int(data["page_count"]),
            total_tokens=int(data["total_tokens"]),
            unique_terms=int(data["unique_terms"]),
            politeness_delay_seconds=float(data["politeness_delay_seconds"]),
        )


@dataclass
class SearchIndex:
    """The complete in-memory search index, fielded.

    ``index`` is keyed first by field name (``text`` / ``author`` / ``tag``),
    then by term, then by ``doc_id``. Each leaf is a :class:`Posting`.
    """

    metadata: IndexMetadata
    documents: dict[str, Document]
    index: dict[str, dict[str, dict[str, Posting]]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "metadata": self.metadata.to_dict(),
            "documents": {
                doc_id: doc.to_dict() for doc_id, doc in self.documents.items()
            },
            "index": {
                field: {
                    term: {
                        doc_id: posting.to_dict()
                        for doc_id, posting in postings.items()
                    }
                    for term, postings in field_index.items()
                }
                for field, field_index in self.index.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchIndex":
        return cls(
            metadata=IndexMetadata.from_dict(data["metadata"]),
            documents={
                doc_id: Document.from_dict(d)
                for doc_id, d in data["documents"].items()
            },
            index={
                field: {
                    term: {
                        doc_id: Posting.from_dict(p)
                        for doc_id, p in postings.items()
                    }
                    for term, postings in field_index.items()
                }
                for field, field_index in data["index"].items()
            },
        )
