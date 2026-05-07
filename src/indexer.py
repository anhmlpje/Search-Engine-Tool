"""Inverted-index construction from crawled pages.

Extracts the indexable semantic content from each page (quote text, author
names, tag lists, and author biographies on /author/ pages), tokenises it,
and produces a :class:`SearchIndex`. Site chrome -- navigation, pagination,
and footer -- is deliberately excluded so that words appearing on every
page do not dominate the index without informing relevance.
"""

from collections.abc import Iterable
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.crawler import Page
from src.models import Document, IndexMetadata, Posting, SearchIndex
from src.utils import tokenize


def extract_text(html: str) -> str:
    """Return the indexable text content of a quotes.toscrape.com page.

    Two layouts are recognised:

    1. List pages (homepage, ``/page/N/``, ``/tag/X/``) carry one or more
       ``.quote`` divs -- text, author, and tag links are kept.
    2. Author detail pages (``/author/Name/``) carry a single
       ``.author-title`` plus an ``.author-description`` biography.

    Anything else (login form, navigation only) yields the empty string,
    which means it contributes no tokens to the index.
    """
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []

    for quote in soup.select(".quote"):
        text_el = quote.select_one(".text")
        author_el = quote.select_one(".author")
        if text_el:
            parts.append(text_el.get_text())
        if author_el:
            parts.append(author_el.get_text())
        for tag in quote.select(".tags .tag"):
            parts.append(tag.get_text())

    title_el = soup.select_one(".author-title")
    if title_el:
        parts.append(title_el.get_text())
    description_el = soup.select_one(".author-description")
    if description_el:
        parts.append(description_el.get_text())

    return " ".join(parts)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_index(
    pages: Iterable[Page],
    base_url: str,
    *,
    politeness_delay_seconds: float = 6.0,
) -> SearchIndex:
    """Consume crawled pages and produce a :class:`SearchIndex`.

    Pages are consumed lazily, so the iterable can come straight from the
    crawler without buffering the whole site in memory. Document IDs are
    assigned in iteration order as ``doc_001``, ``doc_002``, ...
    """
    documents: dict[str, Document] = {}
    index: dict[str, dict[str, Posting]] = {}
    total_tokens = 0

    for ordinal, page in enumerate(pages, start=1):
        doc_id = f"doc_{ordinal:03d}"
        tokens = tokenize(extract_text(page.html))

        documents[doc_id] = Document(
            url=page.url, title=page.title, length=len(tokens)
        )
        total_tokens += len(tokens)

        for position, token in enumerate(tokens):
            postings = index.setdefault(token, {})
            posting = postings.get(doc_id)
            if posting is None:
                posting = Posting(freq=0, positions=[])
                postings[doc_id] = posting
            posting.freq += 1
            posting.positions.append(position)

    metadata = IndexMetadata(
        base_url=base_url,
        created_at=_now_utc_iso(),
        page_count=len(documents),
        total_tokens=total_tokens,
        unique_terms=len(index),
        politeness_delay_seconds=politeness_delay_seconds,
    )

    return SearchIndex(metadata=metadata, documents=documents, index=index)
