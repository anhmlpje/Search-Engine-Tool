"""Manual smoke test: crawl quotes.toscrape.com and report what was found.

Not run in CI; not part of the test suite. Validates that the crawler works
against real HTML by consuming the first few pages from the generator and
stopping early -- a full crawl of the site takes too long for a smoke test
because the politeness window applies to every discovered page.

Invoke:

    PYTHONPATH=. python scripts/smoke_crawler.py
"""

import time

from src.crawler import Crawler

LIMIT = 3


def main() -> None:
    start = time.perf_counter()
    crawler = Crawler("https://quotes.toscrape.com/", delay_seconds=6.0)

    pages = []
    for page in crawler.crawl():
        pages.append(page)
        if len(pages) >= LIMIT:
            break

    elapsed = time.perf_counter() - start
    print(f"fetched {len(pages)} pages in {elapsed:.1f}s")
    print(f"expected ~{(LIMIT - 1) * 6:.0f}s of politeness sleep")
    print("---")
    for page in pages:
        print(f"  {page.url}  title={page.title!r}  bytes={len(page.html)}")


if __name__ == "__main__":
    main()
