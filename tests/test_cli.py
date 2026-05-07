"""Tests for src.main (the interactive CLI shell)."""

import cmd
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from src.main import SearchShell
from src.models import Document, IndexMetadata, Posting, SearchIndex
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
            "doc_001": Document(url="https://x/a", title="A", length=2),
            "doc_002": Document(url="https://x/b", title="B", length=2),
        },
        index={
            "hello": {
                "doc_001": Posting(freq=1, positions=[0]),
                "doc_002": Posting(freq=1, positions=[0]),
            },
            "world": {"doc_001": Posting(freq=1, positions=[1])},
            "friends": {"doc_002": Posting(freq=1, positions=[1])},
        },
    )
    save(index, path)
    return path


@pytest.fixture
def saved_index(tmp_path: Path) -> Path:
    return _saved_index(tmp_path / "idx.json")


class TestUnknownAndEmpty:
    def test_unknown_command(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        out = _drive(shell, "wat")
        assert "unknown command" in out

    def test_empty_line_does_not_repeat(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        # Two blank lines followed by exit -- should not error or echo anything odd
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


class TestFind:
    def test_find_single_term_returns_results(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello")
        assert "https://x/a" in out
        assert "https://x/b" in out

    def test_find_multi_term_intersection(self, saved_index: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", "find hello world")
        # Only doc_001 has both -> only x/a appears in the ranked list.
        # x/b does not appear in find output (it may still appear in load summary, but
        # neither command prints x/b URL).
        assert "https://x/a" in out
        # Find output shouldn't contain doc_002's URL.
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
        # shlex.split raises ValueError on unbalanced quotes; CLI should report it.
        shell = SearchShell(base_url="https://x/", index_path=saved_index)
        out = _drive(shell, "load", 'find "unbalanced')
        assert "error" in out.lower()


class TestExit:
    def test_quit_alias_leaves_loop(self, tmp_path: Path) -> None:
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        # Drive with just "quit" and no "exit" follow-up; cmdloop should exit.
        shell.stdin = io.StringIO("quit\n")
        shell.stdout = io.StringIO()
        shell.use_rawinput = False
        shell.cmdloop(intro="")
        # If it didn't exit, the cmdloop call would block forever; reaching here
        # means quit worked.
        assert True


class TestKeyboardInterrupt:
    def test_ctrl_c_keeps_shell_alive(self, tmp_path: Path) -> None:
        """Ctrl+C should be caught: the shell prints a hint and re-enters
        the loop rather than letting the KeyboardInterrupt escape."""
        shell = SearchShell(base_url="https://x/", index_path=tmp_path / "i.json")
        shell.stdout = io.StringIO()

        call_count = {"n": 0}

        def fake_inner_cmdloop(self: cmd.Cmd, intro: object | None = None) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise KeyboardInterrupt
            # Second entry: simulate a normal clean exit (e.g. user typed quit).
            return None

        with patch.object(cmd.Cmd, "cmdloop", fake_inner_cmdloop):
            shell.cmdloop(intro="")

        assert call_count["n"] == 2
        assert "^C" in shell.stdout.getvalue()
        assert "exit" in shell.stdout.getvalue()
