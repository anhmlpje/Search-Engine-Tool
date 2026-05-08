"""Field-aware inverted-index construction from crawled pages.

Each indexed document is split into three named fields -- ``text``,
``author``, and ``tag`` -- with independent token streams and posting
lists. This lets the search layer route ``field:term`` queries and lets
``find`` show a context snippet drawn from the stored ``text`` tokens
without re-parsing HTML.
"""

from collections.abc import Iterable
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.crawler import Page
from src.models import (
    Document,
    FieldData,
    IndexMetadata,
    Posting,
    SearchIndex,
)
from src.utils import tokenize


FIELD_NAMES = ("text", "author", "tag")


def extract_fields(html: str) -> dict[str, str]:
    """Return per-field text content for a quotes.toscrape.com page.

    On list pages (homepage, ``/page/N/``, ``/tag/X/``) each ``.quote``
    block contributes its ``.text`` to the *text* field, its ``.author``
    to the *author* field, and each ``.tag`` to the *tag* field. On
    author detail pages (``/author/Name/``) the ``.author-title`` is added
    to the *author* field and the ``.author-description`` body to the
    *text* field. Site chrome (navigation, pagination, footer) is
    ignored, as documented in design_notes.md.
    """
    soup = BeautifulSoup(html, "html.parser")
    text_parts: list[str] = []
    author_parts: list[str] = []
    tag_parts: list[str] = []

    for quote in soup.select(".quote"):
        text_el = quote.select_one(".text")
        if text_el:
            text_parts.append(text_el.get_text())
        author_el = quote.select_one(".author")
        if author_el:
            author_parts.append(author_el.get_text())
        for tag in quote.select(".tags .tag"):
            tag_parts.append(tag.get_text())

    title_el = soup.select_one(".author-title")
    if title_el:
        author_parts.append(title_el.get_text())
    description_el = soup.select_one(".author-description")
    if description_el:
        text_parts.append(description_el.get_text())

    return {
        "text": " ".join(text_parts),
        "author": " ".join(author_parts),
        "tag": " ".join(tag_parts),
    }


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_index(
    pages: Iterable[Page],
    base_url: str,
    *,
    politeness_delay_seconds: float = 6.0,
) -> SearchIndex:
    """Consume crawled pages and produce a fielded :class:`SearchIndex`.

    Pages are consumed lazily so the iterable can come straight from the
    crawler. Document IDs are assigned in iteration order as ``doc_001``,
    ``doc_002``, ...
    """
    documents: dict[str, Document] = {}
    index: dict[str, dict[str, dict[str, Posting]]] = {
        name: {} for name in FIELD_NAMES
    }
    total_tokens = 0

    for ordinal, page in enumerate(pages, start=1):
        doc_id = f"doc_{ordinal:03d}"
        fields_text = extract_fields(page.html)

        field_data: dict[str, FieldData] = {}
        for field_name in FIELD_NAMES:
            tokens = tokenize(fields_text.get(field_name, ""))
            field_data[field_name] = FieldData(length=len(tokens), tokens=tokens)

            field_index = index[field_name]
            for position, token in enumerate(tokens):
                postings = field_index.setdefault(token, {})
                posting = postings.get(doc_id)
                if posting is None:
                    posting = Posting(freq=0, positions=[])
                    postings[doc_id] = posting
                posting.freq += 1
                posting.positions.append(position)

        doc_total = sum(fd.length for fd in field_data.values())
        documents[doc_id] = Document(
            url=page.url,
            title=page.title,
            length=doc_total,
            fields=field_data,
        )
        total_tokens += doc_total

    # Unique terms is the union across fields: a term appearing in both
    # text and tag is counted once.
    all_terms: set[str] = set()
    for field_index in index.values():
        all_terms.update(field_index.keys())

    metadata = IndexMetadata(
        base_url=base_url,
        created_at=_now_utc_iso(),
        page_count=len(documents),
        total_tokens=total_tokens,
        unique_terms=len(all_terms),
        politeness_delay_seconds=politeness_delay_seconds,
    )

    return SearchIndex(metadata=metadata, documents=documents, index=index)
