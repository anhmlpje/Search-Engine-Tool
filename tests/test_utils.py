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

    @responses.activate
    def test_sleeps_between_retries_when_clock_provided(self) -> None:
        """The brief's politeness window applies to retries too: each retry
        attempt is itself a request to the same host, so the helper must
        sleep ``retry_delay`` seconds before each retry when a clock is
        given. The first attempt is not preceded by a sleep."""

        class FakeClock:
            def __init__(self) -> None:
                self.calls: list[float] = []

            def sleep(self, seconds: float) -> None:
                self.calls.append(seconds)

        responses.add(responses.GET, "https://example.com/", status=500)
        responses.add(responses.GET, "https://example.com/", status=500)
        responses.add(responses.GET, "https://example.com/", body="ok", status=200)
        clock = FakeClock()
        response = safe_request(
            "https://example.com/",
            retries=2,
            clock=clock,
            retry_delay=6.0,
        )
        assert response.status_code == 200
        # Two retries -> two sleeps before retry attempts 2 and 3.
        assert clock.calls == [6.0, 6.0]

    @responses.activate
    def test_sleeps_before_each_retry_even_when_all_fail(self) -> None:
        class FakeClock:
            def __init__(self) -> None:
                self.calls: list[float] = []

            def sleep(self, seconds: float) -> None:
                self.calls.append(seconds)

        for _ in range(3):
            responses.add(responses.GET, "https://example.com/", status=500)
        clock = FakeClock()
        with pytest.raises(HttpError):
            safe_request(
                "https://example.com/",
                retries=2,
                clock=clock,
                retry_delay=6.0,
            )
        # Even on total failure, the politeness sleeps before retries 2 and 3
        # must have happened so the host did not see three back-to-back GETs.
        assert clock.calls == [6.0, 6.0]
