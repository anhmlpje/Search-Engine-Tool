"""Tests for src.main (the interactive CLI shell)."""

import cmd
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from src.main import SearchShell
from src.models import (
    Document,
    FieldData,
    IndexMetadata,
    Posting,
    SearchIndex,
)
from src.storage import save


def _drive(shell: SearchShell, *commands: str) -> str:
    """Feed scripted lines into the shell and return everything written to stdout."""
    stdin_text = "\n".join(commands) + "\nexit\n"
    shell.stdin = io.StringIO(stdin_text)
    shell.stdout = io.StringIO()
    shell.use_rawinput = False
    shell.cmdloop(intro="")
    return shell.stdout.getvalue()


def _saved_index(path: Path) -> Path:
    index = SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=2,
            total_tokens=4,
            unique_terms=3,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(
                url="https://x/a",
                title="A",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["hello", "world"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/b",
                title="B",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["hello", "friends"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
                "hello": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
                "world": {"doc_001": Posting(freq=1, positions=[1])},
                "friends": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "author": {},
            "tag": {},
        },
    )
    save(index, path)
    return path


def _saved_phrase_index(path: Path) -> Path:
    """Index where 'good friends' appears as an adjacent phrase in doc_001."""
    index = SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=2,
            total_tokens=5,
            unique_terms=3,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(
                url="https://x/a",
                title="A",
                length=2,
                fields={
                    "text": FieldData(length=2, tokens=["good", "friends"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/b",
                title="B",
                length=3,
                fields={
                    "text": FieldData(length=3, tokens=["good", "big", "friends"]),
                    "author": FieldData(length=0, tokens=[]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
                "good": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
                "friends": {
                    "doc_001": Posting(freq=1, positions=[1]),
                    "doc_002": Posting(freq=1, positions=[2]),
                },
                "big": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "author": {},
            "tag": {},
        },
    )
    save(index, path)
    return path


def _saved_fielded_index(path: Path) -> Path:
    """Index demonstrating field:term routing in CLI."""
    index = SearchIndex(
        metadata=IndexMetadata(
            base_url="https://x/",
            created_at="2026-05-07T12:34:56Z",
            page_count=2,
            total_tokens=8,
            unique_terms=4,
            politeness_delay_seconds=6.0,
        ),
        documents={
            "doc_001": Document(
                url="https://x/wilde",
                title="Wilde",
                length=4,
                fields={
                    "text": FieldData(length=2, tokens=["love", "endures"]),
                    "author": FieldData(length=2, tokens=["oscar", "wilde"]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
            "doc_002": Document(
                url="https://x/twain",
                title="Twain",
                length=4,
                fields={
                    "text": FieldData(length=2, tokens=["love", "wins"]),
                    "author": FieldData(length=2, tokens=["mark", "twain"]),
                    "tag": FieldData(length=0, tokens=[]),
                },
            ),
        },
        index={
            "text": {
                "love": {
                    "doc_001": Posting(freq=1, positions=[0]),
                    "doc_002": Posting(freq=1, positions=[0]),
                },
                "endures": {"doc_001": Posting(freq=1, positions=[1])},
                "wins": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "author": {
                "oscar": {"doc_001": Posting(freq=1, positions=[0])},
                "wilde": {"doc_001": Posting(freq=1, positions=[1])},
                "mark": {"doc_002": Posting(freq=1, positions=[0])},
                "twain": {"doc_002": Posting(freq=1, positions=[1])},
            },
            "tag": {},
        },
    )
    save(index, path)
    return path


@pytest.fixture
def saved_index(tmp_path: Path) -> Path:
    return _saved_index(tmp_path / "idx.json")


@pytest.fixture
def saved_phrase_index(tmp_path: Path) -> Path:
    return _saved_phrase_index(tmp_path / "phrase.json")


@pytest.fixture
def saved_fielded_index(tmp_path: Path) -> Path:
    return _saved_fielded_index(tmp_path / "fielded.json")


class TestUnknownAndEmpty:
    def test_unknown_command(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        out = _drive(shell, "wat")
        assert "unknown command" in out

    def test_empty_line_does_not_repeat(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        out = _drive(shell, "", "")
        assert "unknown command" not in out


class TestNoIndexLoaded:
    def test_print_before_load(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        out = _drive(shell, "print hello")
        assert "no index loaded" in out

    def test_find_before_load(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        out = _drive(shell, "find hello")
        assert "no index loaded" in out


class TestLoad:
    def test_load_missing_file_reports_clearly(self, tmp_path: Path) -> None:
        shell = SearchShell(
            base_url="https://x/", index_path=tmp_path / "missing.json"
        )
        out = _drive(shell, "load")
        assert "not found" in out

    def test_load_corrupt_file_reports_clearly(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        shell = SearchShell(base_url="https://x/", index_path=path)
        out = _drive(shell, "load")
        assert "error" in out.lower()

    def test_load_succeeds_and_reports_summary(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load")
        assert "[loaded]" in out
        assert "pages=2" in out


class TestPrint:
    def test_print_known_word(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "print hello")
        assert "hello" in out
        assert "doc_001" in out
        assert "doc_002" in out

    def test_print_unknown_word(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "print xyz123")
        assert "no matches" in out

    def test_print_empty_argument(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "print")
        assert "usage" in out

    def test_print_strips_punctuation_via_tokenizer(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "print hello!")
        assert "doc_001" in out
        assert "no matches" not in out


class TestFind:
    def test_find_single_term_returns_results(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello")
        assert "https://x/a" in out
        assert "https://x/b" in out

    def test_find_multi_term_intersection(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello world")
        assert "https://x/a" in out
        find_section = out.split("[loaded]")[-1]
        assert "https://x/b" not in find_section

    def test_find_no_matches(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find xyz123")
        assert "no matches" in out

    def test_find_empty_query(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find")
        assert "usage" in out

    def test_find_malformed_quote(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", 'find "unbalanced')
        assert "error" in out.lower()

    def test_find_strips_punctuation_via_tokenizer(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello!")
        find_section = out.split("[loaded]")[-1]
        assert "https://x/a" in find_section
        assert "no matches" not in find_section

    def test_find_punctuation_only_query_says_usage(
        self, saved_index: Path
    ) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find !!!")
        find_section = out.split("[loaded]")[-1]
        # All input items tokenise to nothing -> no matches (or usage)
        assert "no matches" in find_section or "usage" in find_section

    def test_find_emits_snippet(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello")
        assert "[HELLO]" in out


class TestFindPhrase:
    def test_quoted_phrase_routes_to_phrase_search(
        self, saved_phrase_index: Path
    ) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_phrase_index)
        out = _drive(shell, "load", 'find "good friends"')
        find_section = out.split("[loaded]")[-1]
        assert "https://x/a" in find_section
        assert "https://x/b" not in find_section
        assert "occurrences=1" in find_section

    def test_phrase_with_no_match_says_no_matches(
        self, saved_phrase_index: Path
    ) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_phrase_index)
        out = _drive(shell, "load", 'find "friends good"')
        find_section = out.split("[loaded]")[-1]
        assert "no matches" in find_section

    def test_unquoted_multi_word_uses_and_not_phrase(
        self, saved_phrase_index: Path
    ) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_phrase_index)
        out = _drive(shell, "load", "find good friends")
        find_section = out.split("[loaded]")[-1]
        assert "https://x/a" in find_section
        assert "https://x/b" in find_section
        assert "tfidf=" in find_section


class TestFieldedFind:
    def test_field_prefix_filters_by_field(
        self, saved_fielded_index: Path
    ) -> None:
        shell = SearchShell(
            base_url="https://x/", index_path=saved_fielded_index
        )
        out = _drive(shell, "load", "find author:wilde")
        find_section = out.split("[loaded]")[-1]
        assert "https://x/wilde" in find_section
        assert "https://x/twain" not in find_section

    def test_combining_bare_and_fielded_terms(
        self, saved_fielded_index: Path
    ) -> None:
        # 'love' is in both docs; author:wilde restricts to doc_001
        shell = SearchShell(
            base_url="https://x/", index_path=saved_fielded_index
        )
        out = _drive(shell, "load", "find love author:wilde")
        find_section = out.split("[loaded]")[-1]
        assert "https://x/wilde" in find_section
        assert "https://x/twain" not in find_section

    def test_unknown_field_returns_no_matches(
        self, saved_fielded_index: Path
    ) -> None:
        shell = SearchShell(
            base_url="https://x/", index_path=saved_fielded_index
        )
        out = _drive(shell, "load", "find unknown:wilde")
        find_section = out.split("[loaded]")[-1]
        assert "no matches" in find_section


class TestExplainFlag:
    def test_explain_prints_per_term_breakdown(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find --explain hello")
        find_section = out.split("[loaded]")[-1]
        # Without --explain, none of these tokens appear; with --explain, all do.
        assert "tf=" in find_section
        assert "idf=" in find_section
        assert "tfidf=" in find_section
        assert "freq=" in find_section

    def test_default_output_omits_breakdown(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello")
        find_section = out.split("[loaded]")[-1]
        # The default summary line contains 'tfidf=' as the score label, so
        # we look for the breakdown-specific tokens that only show under
        # --explain: a 'freq=' field on its own line plus a standalone 'tf='.
        assert "freq=" not in find_section
        assert " tf=" not in find_section

    def test_explain_silently_ignored_for_phrase(
        self, saved_phrase_index: Path
    ) -> None:
        shell = SearchShell(
            base_url="https://x/", index_path=saved_phrase_index
        )
        out = _drive(shell, "load", 'find --explain "good friends"')
        find_section = out.split("[loaded]")[-1]
        # Phrase mode still triggers, score label is "occurrences", and no
        # tfidf breakdown lines are emitted.
        assert "occurrences=1" in find_section
        assert "tf=" not in find_section

    def test_explain_position_within_args_is_flexible(
        self, saved_index: Path
    ) -> None:
        # --explain after the terms should work the same as before.
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello --explain")
        find_section = out.split("[loaded]")[-1]
        assert "tf=" in find_section


class TestExit:
    def test_quit_alias_leaves_loop(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        shell.stdin = io.StringIO("quit\n")
        shell.stdout = io.StringIO()
        shell.use_rawinput = False
        shell.cmdloop(intro="")
        assert True


class TestKeyboardInterrupt:
    def test_ctrl_c_keeps_shell_alive(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        shell.stdout = io.StringIO()

        call_count = {"n": 0}

        def fake_inner_cmdloop(self: cmd.Cmd, intro: object | None = None) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise KeyboardInterrupt
            return None

        with patch.object(cmd.Cmd, "cmdloop", fake_inner_cmdloop):
            shell.cmdloop(intro="")

        assert call_count["n"] == 2
        assert "^C" in shell.stdout.getvalue()
        assert "exit" in shell.stdout.getvalue()
