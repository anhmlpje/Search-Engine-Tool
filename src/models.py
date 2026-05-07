"""Data classes for documents, postings, metadata, and the search index.

These classes know how to convert themselves to and from plain ``dict``
representations so that the storage layer (Phase 3) can serialise the index
to JSON without needing to know any of the field details.
"""

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class Document:
    """A single crawled page registered in the index."""

    url: str
    title: str
    length: int  # number of tokens after tokenisation

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "title": self.title, "length": self.length}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        return cls(url=data["url"], title=data["title"], length=data["length"])


@dataclass
class Posting:
    """A single ``(term, document)`` entry in the inverted index."""

    freq: int
    positions: list[int]  # zero-indexed token offsets in the document

    def to_dict(self) -> dict[str, Any]:
        return {"freq": self.freq, "positions": list(self.positions)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Posting":
        return cls(freq=int(data["freq"]), positions=list(data["positions"]))


@dataclass
class IndexMetadata:
    """Top-level index summary for the on-disk JSON file."""

    base_url: str
    created_at: str  # ISO 8601 UTC, e.g. "2026-05-07T12:34:56Z"
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
    """The complete in-memory search index.

    The on-disk JSON form is produced by :meth:`to_dict`, which embeds
    :data:`SCHEMA_VERSION` so that the storage layer can validate the file
    on load.
    """

    metadata: IndexMetadata
    documents: dict[str, Document]  # doc_id -> Document
    index: dict[str, dict[str, Posting]]  # term -> doc_id -> Posting

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "metadata": self.metadata.to_dict(),
            "documents": {
                doc_id: doc.to_dict() for doc_id, doc in self.documents.items()
            },
            "index": {
                term: {
                    doc_id: posting.to_dict() for doc_id, posting in postings.items()
                }
                for term, postings in self.index.items()
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
                term: {
                    doc_id: Posting.from_dict(p) for doc_id, p in postings.items()
                }
                for term, postings in data["index"].items()
            },
        )
