"""Tests for src.utils."""

import pytest
import responses

from src.utils import HttpError, RealClock, safe_request, tokenize


class TestTokenize:
    def test_empty_input(self) -> None:
        assert tokenize("") == []

    def test_punctuation_only(self) -> None:
        assert tokenize("!!! ... ???") == []

    def test_lowercases_mixed_case(self) -> None:
        assert tokenize("The Quick Brown Fox") == ["the", "quick", "brown", "fox"]

    def test_curly_apostrophe_splits_word(self) -> None:
        # U+2019 is punctuation, not a word character
        assert tokenize("don’t") == ["don", "t"]

    def test_straight_apostrophe_splits_word(self) -> None:
        assert tokenize("don't") == ["don", "t"]

    def test_unicode_letter_preserved(self) -> None:
        # Non-ASCII letters are word characters under Python 3 Unicode \w
        assert tokenize("café résumé") == ["café", "résumé"]

    def test_digits_are_tokens(self) -> None:
        assert tokenize("abc 123 mix3d") == ["abc", "123", "mix3d"]

    def test_underscore_kept_inside_token(self) -> None:
        assert tokenize("snake_case") == ["snake_case"]

    def test_multiple_whitespace_collapsed(self) -> None:
        assert tokenize("a    b\tc\nd") == ["a", "b", "c", "d"]


class TestRealClock:
    def test_sleep_zero_does_not_raise(self) -> None:
        RealClock().sleep(0)


class TestSafeRequest:
    @responses.activate
    def test_returns_response_on_success(self) -> None:
        responses.add(responses.GET, "https://example.com/", body="ok", status=200)
        response = safe_request("https://example.com/")
        assert response.status_code == 200
        assert response.text == "ok"

    @responses.activate
    def test_retries_until_success(self) -> None:
        responses.add(responses.GET, "https://example.com/", status=500)
        responses.add(responses.GET, "https://example.com/", body="ok", status=200)
        response = safe_request("https://example.com/", retries=1)
        assert response.status_code == 200
        assert len(responses.calls) == 2

    @responses.activate
    def test_raises_after_retries_exhausted(self) -> None:
        for _ in range(3):
            responses.add(responses.GET, "https://example.com/", status=500)
        with pytest.raises(HttpError):
            safe_request("https://example.com/", retries=2)
        assert len(responses.calls) == 3

    @responses.activate
    def test_raises_on_connection_error(self) -> None:
        # No mock registered -> responses raises ConnectionError, which is a
        # RequestException and therefore retried then wrapped in HttpError.
        with pytest.raises(HttpError):
            safe_request("https://no-such-host.invalid/", retries=0)
