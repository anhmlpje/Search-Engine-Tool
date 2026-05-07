"""Micro-benchmarks for the search engine's hot paths.

Run with ``pytest tests/test_performance.py --benchmark-only`` to get a
human-readable table of mean / stddev / iterations per operation. The
numbers shown in README's performance section come from running this
suite locally on the project conda environment.

These tests do not assert correctness -- the rest of the suite covers
that -- and they do not fail on regression by default. Their purpose is
to surface the runtime characteristics of the four hot paths so the
README's complexity claims are grounded in measurement, not assertion.
"""

import pytest

from src.crawler import Page
from src.indexer import build_index
from src.models import SearchIndex
from src.search import find, find_phrase, print_word

# A synthetic 50-page corpus with a vocabulary of around 80 terms,
# enough to make the benchmark meaningful but small enough to fit in
# memory many times over.
_VOCAB = [
    "good",
    "friends",
    "love",
    "indifference",
    "philosophy",
    "wisdom",
    "humour",
    "life",
    "truth",
    "books",
    "world",
    "people",
    "thought",
    "freedom",
    "courage",
    "hope",
]


def _synthetic_pages(count: int = 50) -> list[Page]:
    """Build ``count`` quote pages, each containing two synthetic quotes."""
    pages: list[Page] = []
    for i in range(count):
        # Pick a few terms cyclically so frequencies vary across pages.
        first = _VOCAB[i % len(_VOCAB)]
        second = _VOCAB[(i + 3) % len(_VOCAB)]
        third = _VOCAB[(i + 7) % len(_VOCAB)]
        html = (
            "<html><body>"
            f'<div class="quote">'
            f'<span class="text">"{first} and {second} are {third}."</span>'
            f'<span><small class="author">Author{i}</small></span>'
            f'<div class="tags">'
            f'<a class="tag" href="/tag/{first}/">{first}</a>'
            f'<a class="tag" href="/tag/{third}/">{third}</a>'
            f"</div></div>"
            f'<div class="quote">'
            f'<span class="text">"good {second} make good {first}."</span>'
            f'<span><small class="author">Author{i}</small></span>'
            f"</div>"
            "</body></html>"
        )
        pages.append(Page(url=f"https://site.test/p/{i}", html=html, title=f"P{i}"))
    return pages


@pytest.fixture(scope="module")
def synthetic_pages() -> list[Page]:
    return _synthetic_pages(50)


@pytest.fixture(scope="module")
def benchmark_index(synthetic_pages: list[Page]) -> SearchIndex:
    return build_index(iter(synthetic_pages), base_url="https://site.test/")


class TestBenchmarks:
    def test_build_index_50_pages(self, benchmark, synthetic_pages: list[Page]) -> None:
        benchmark(lambda: build_index(iter(synthetic_pages), base_url="https://site.test/"))

    def test_single_word_lookup(self, benchmark, benchmark_index: SearchIndex) -> None:
        benchmark(lambda: benchmark_index.index.get("good"))

    def test_print_word(self, benchmark, benchmark_index: SearchIndex) -> None:
        benchmark(lambda: print_word(benchmark_index, "good"))

    def test_find_and_three_terms(self, benchmark, benchmark_index: SearchIndex) -> None:
        benchmark(lambda: find(benchmark_index, ["good", "friends", "love"]))

    def test_find_phrase_two_words(self, benchmark, benchmark_index: SearchIndex) -> None:
        benchmark(lambda: find_phrase(benchmark_index, "good friends"))
