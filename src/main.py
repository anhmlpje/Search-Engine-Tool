"""Interactive command-line shell for the search engine tool.

Run with ``python -m src.main``. The four primary commands are ``build``,
``load``, ``print``, and ``find``; ``help``, ``stats``, and ``exit`` are
auxiliary. Errors are reported as plain messages; the shell never crashes
on unknown commands or malformed input.
"""

import cmd
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path

from src.crawler import Crawler, Page
from src.indexer import build_index
from src.models import SearchIndex
from src.search import find, find_phrase, print_word
from src.storage import (
    IndexCorrupt,
    IndexNotFound,
    SchemaMismatch,
    load,
    save,
)
from src.utils import tokenize  # used by do_print to normalise input

DEFAULT_INDEX_PATH = Path("data/index.json")
DEFAULT_BASE_URL = "https://quotes.toscrape.com/"
DEFAULT_DELAY_SECONDS = 6.0


class SearchShell(cmd.Cmd):
    """REPL exposing build, load, print, find, plus a few helpers."""

    intro = "Search Engine Tool. Type help or ? to list commands."
    prompt = "> "

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        index_path: Path | str = DEFAULT_INDEX_PATH,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        completekey: str = "tab",
        stdin: object | None = None,
        stdout: object | None = None,
    ) -> None:
        super().__init__(completekey=completekey, stdin=stdin, stdout=stdout)  # type: ignore[arg-type]
        self.base_url = base_url
        self.index_path = Path(index_path)
        self.delay_seconds = delay_seconds
        self.index: SearchIndex | None = None

    # --- Output helpers ---------------------------------------------------

    def _emit(self, message: str = "") -> None:
        self.stdout.write(message + "\n")

    def _emit_index_summary(self, index: SearchIndex, prefix: str) -> None:
        meta = index.metadata
        self._emit(
            f"{prefix} pages={meta.page_count} "
            f"tokens={meta.total_tokens} terms={meta.unique_terms}"
        )

    # --- Crawl + index hook (overridable for tests) -----------------------

    def _crawl_pages(self) -> Iterator[Page]:
        crawler = Crawler(self.base_url, delay_seconds=self.delay_seconds)
        for page in crawler.crawl():
            self._emit(f"[fetch] {page.url}")
            yield page

    # --- Commands ---------------------------------------------------------

    def do_build(self, _arg: str) -> None:
        """Crawl the target site, build the inverted index, and save to disk."""
        self._emit(f"[build] crawling {self.base_url}")
        index = build_index(
            self._crawl_pages(),
            base_url=self.base_url,
            politeness_delay_seconds=self.delay_seconds,
        )
        save(index, self.index_path)
        self.index = index
        self._emit_index_summary(index, "[built]")
        self._emit(f"[saved] {self.index_path}")

    def do_load(self, _arg: str) -> None:
        """Load the previously built index from disk."""
        try:
            index = load(self.index_path)
        except IndexNotFound:
            self._emit(
                f"error: index file not found at {self.index_path}; "
                "run 'build' first"
            )
            return
        except SchemaMismatch as exc:
            self._emit(f"error: {exc}")
            return
        except IndexCorrupt as exc:
            self._emit(f"error: {exc}")
            return
        self.index = index
        self._emit_index_summary(index, "[loaded]")

    def do_print(self, arg: str) -> None:
        """Show the posting list for a single word: ``print <word>``."""
        if self.index is None:
            self._emit("no index loaded; run 'load' or 'build' first")
            return
        # Run the input through the same tokeniser used at index time so
        # that "print good!" matches the indexed word "good", and so that
        # apostrophes/punctuation behave consistently with the index.
        tokens = tokenize(arg)
        if not tokens:
            self._emit("usage: print <word>")
            return
        self._emit(print_word(self.index, tokens[0]))

    def do_find(self, arg: str) -> None:
        """Find pages by AND query or quoted phrase.

        ``find good friends``     -> AND of two terms, ranked by TF-IDF
        ``find "good friends"``   -> phrase match, ranked by occurrences
        """
        if self.index is None:
            self._emit("no index loaded; run 'load' or 'build' first")
            return
        try:
            items = shlex.split(arg)
        except ValueError as exc:
            self._emit(f"error: {exc}")
            return
        if not items:
            self._emit("usage: find <term> [term ...]   or   find \"<phrase>\"")
            return

        # A single quoted multi-word string -> phrase mode (find_phrase
        # tokenises internally, so trailing punctuation inside the phrase
        # is handled there).
        if len(items) == 1 and " " in items[0]:
            results = find_phrase(self.index, items[0])
            mode = "phrase"
        else:
            # find() parses field:term syntax and tokenises the term half
            # internally, so we pass the raw items through unchanged.
            results = find(self.index, items)
            mode = "and"

        if not results:
            self._emit("no matches")
            return
        for result in results:
            matched = " ".join(
                f"{term}={count}" for term, count in result.matched_terms.items()
            )
            score_label = "occurrences" if mode == "phrase" else "tfidf"
            self._emit(
                f"{result.rank}. {result.url}  "
                f"{score_label}={result.score:g}  matched=[{matched}]"
            )
            if result.snippet:
                self._emit(f"   {result.snippet}")

    def do_stats(self, _arg: str) -> None:
        """Show the index summary plus the 20 most frequent tokens.

        Useful for sanity-checking that tokenisation produced a
        language-like distribution (Zipf's law) on the indexed corpus.
        """
        if self.index is None:
            self._emit("no index loaded; run 'load' or 'build' first")
            return
        self._emit_index_summary(self.index, "[stats]")

        # Aggregate term frequency across every field, so that a token
        # appearing in both text and tag is summed.
        per_term: dict[str, int] = {}
        for field_index in self.index.index.values():
            for term, postings in field_index.items():
                per_term[term] = per_term.get(term, 0) + sum(
                    p.freq for p in postings.values()
                )
        term_totals = sorted(per_term.items(), key=lambda t: (-t[1], t[0]))

        self._emit("top 20 tokens by total corpus frequency:")
        for rank, (term, total) in enumerate(term_totals[:20], start=1):
            self._emit(f"  {rank:>2}. {term:<20s} {total}")

    def do_exit(self, _arg: str) -> bool:
        """Leave the shell."""
        return True

    def do_quit(self, _arg: str) -> bool:
        """Leave the shell."""
        return True

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> None:
        head = line.split(maxsplit=1)[0] if line.split() else ""
        self._emit(f"unknown command: {head}")
        self._emit("type 'help' for available commands")

    def cmdloop(self, intro: object | None = None) -> None:
        """Wrap the inherited loop so Ctrl+C cancels the current input
        without exiting the shell -- the user must type 'exit' or 'quit'
        to leave, matching the conventions of the Python and SQLite REPLs.
        """
        while True:
            try:
                super().cmdloop(intro=intro)
            except KeyboardInterrupt:
                self._emit("")
                self._emit("^C (type 'exit' or 'quit' to leave the shell)")
                intro = None
                continue
            break


def main() -> int:
    SearchShell().cmdloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
