"""Tests for the Kagi search result parsing helpers."""

import pytest

from born_portal.utils.search import (
    KagiAuthError,
    looks_challenged,
    looks_unauthenticated,
    normalize_session_token,
    parse_search_results,
)

_RESULTS_HTML = """
<html><body>
  <div class="search-result">
    <a class="__sri_title_link" href="https://example.com/one">First result</a>
    <div class="__sri-desc">
      <span class="__sri-time">Oct 4, 2026</span>
      A snippet with a <a class="summarize-link">summary</a> link.
    </div>
  </div>
  <div class="sr-group">
    <div class="__srgi">
      <div class="__srgi-title">
        <a href="https://example.com/two">Second result</a>
      </div>
      <div class="__sri-desc">
        <span class="__sri-time">Yesterday</span>
        Relative date stays in the snippet.
      </div>
    </div>
  </div>
</body></html>
"""


def test_normalize_session_token_accepts_raw_token():
    assert normalize_session_token("  abc123  ") == "abc123"


def test_normalize_session_token_extracts_token_from_link():
    token = "https://kagi.com/search?token=abc123&q=rust"
    assert normalize_session_token(token) == "abc123"


def test_normalize_session_token_drops_trailing_query_parameters():
    assert normalize_session_token("abc123&q=%s") == "abc123"


def test_looks_challenged_detects_turnstile_redirect():
    assert looks_challenged("https://kagi.com/turnstile?r=/html/search%3Fq%3Dlinux")
    assert not looks_challenged("https://kagi.com/html/search?q=linux")


@pytest.mark.parametrize("value", ["", "   ", "https://kagi.com/search?q=rust"])
def test_normalize_session_token_rejects_invalid_values(value):
    with pytest.raises(KagiAuthError):
        normalize_session_token(value)


def test_parse_search_results_reads_primary_and_grouped_blocks():
    results = parse_search_results(_RESULTS_HTML)

    assert [result["title"] for result in results] == [
        "First result",
        "Second result",
    ]
    assert [result["rank"] for result in results] == [1, 2]
    assert results[0]["url"] == "https://example.com/one"
    assert results[0]["published"] == "2026-10-04T00:00:00Z"
    # The absolute date and summarize link are stripped from the snippet.
    assert results[0]["snippet"] == "A snippet with a link."
    # A relative date is not converted and remains in the snippet.
    assert results[1]["published"] is None
    assert "Yesterday" in results[1]["snippet"]


def test_looks_unauthenticated_requires_all_markers():
    assert looks_unauthenticated(
        "<title>Kagi Search - A Premium Search Engine</title>"
        "Welcome to Kagi paid search engine that gives power back to the user"
    )
    assert not looks_unauthenticated("<title>rust async - Kagi Search</title>")
