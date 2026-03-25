"""Unit tests for news_grab module."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from mcp_news import server as news_grab


# ---------------------------------------------------------------------------
# Country resolution
# ---------------------------------------------------------------------------


class TestResolveCountryCode:
    def test_iso3_direct(self):
        assert news_grab._resolve_country_code("FRA") == "FRA"
        assert news_grab._resolve_country_code("usa") == "USA"

    def test_full_name(self):
        assert news_grab._resolve_country_code("France") == "FRA"
        assert news_grab._resolve_country_code("United States") == "USA"

    def test_alias(self):
        assert news_grab._resolve_country_code("uk") == "GBR"
        assert news_grab._resolve_country_code("états-unis") == "USA"
        assert news_grab._resolve_country_code("allemagne") == "DEU"

    def test_prefix_match(self):
        assert news_grab._resolve_country_code("switz") == "CHE"

    def test_unknown(self):
        assert news_grab._resolve_country_code("atlantis") is None

    def test_whitespace(self):
        assert news_grab._resolve_country_code("  FRA  ") == "FRA"


# ---------------------------------------------------------------------------
# RSS date parsing
# ---------------------------------------------------------------------------


class TestParseRssDate:
    def test_rfc2822(self):
        dt = news_grab._parse_rss_date("Mon, 01 Jan 2024 12:00:00 +0000")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1

    def test_iso8601_with_tz(self):
        dt = news_grab._parse_rss_date("2024-06-15T10:30:00+02:00")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6

    def test_iso8601_utc_z(self):
        dt = news_grab._parse_rss_date("2024-03-20T08:00:00Z")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_date_only(self):
        dt = news_grab._parse_rss_date("2024-01-15")
        assert dt is not None
        assert dt.year == 2024

    def test_empty_string(self):
        assert news_grab._parse_rss_date("") is None

    def test_garbage(self):
        assert news_grab._parse_rss_date("not a date") is None


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------


class TestCleanHtmlTags:
    def test_strips_tags(self):
        assert news_grab._clean_html_tags("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        assert news_grab._clean_html_tags("  hello   world  ") == "hello world"

    def test_empty(self):
        assert news_grab._clean_html_tags("") == ""


# ---------------------------------------------------------------------------
# RSS XML parsing
# ---------------------------------------------------------------------------

_RSS_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <item>
          <title>Article One</title>
          <link>https://example.com/1</link>
          <description>&lt;p&gt;First article&lt;/p&gt;</description>
          <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
        </item>
        <item>
          <title>Article Two</title>
          <link>https://example.com/2</link>
          <pubDate>Tue, 02 Jan 2024 14:00:00 +0000</pubDate>
        </item>
      </channel>
    </rss>
""").encode("utf-8")

_ATOM_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom Feed</title>
      <entry>
        <title>Atom Article</title>
        <link href="https://example.com/atom/1"/>
        <summary>An atom summary</summary>
        <published>2024-05-10T09:00:00Z</published>
      </entry>
    </feed>
""").encode("utf-8")


class TestParseRssXml:
    def test_rss2(self):
        meta = {"name": "TestSource", "url": "https://feed.example.com", "country": "France"}
        articles = news_grab._parse_rss_xml(_RSS_XML, meta)
        assert len(articles) == 2
        assert articles[0]["title"] == "Article One"
        assert articles[0]["url"] == "https://example.com/1"
        assert articles[0]["source_name"] == "TestSource"
        assert articles[0]["country"] == "France"
        assert articles[0]["published_at"] is not None

    def test_atom(self):
        meta = {"name": "AtomSource", "url": "https://atom.example.com", "country": "Germany"}
        articles = news_grab._parse_rss_xml(_ATOM_XML, meta)
        assert len(articles) == 1
        assert articles[0]["title"] == "Atom Article"
        assert articles[0]["url"] == "https://example.com/atom/1"

    def test_invalid_xml(self):
        articles = news_grab._parse_rss_xml(b"not xml", {"url": "bad"})
        assert articles == []

    def test_skips_items_without_title_and_link(self):
        xml = b"""<?xml version="1.0"?>
        <rss><channel>
          <item><description>No title or link</description></item>
        </channel></rss>"""
        articles = news_grab._parse_rss_xml(xml, {"url": "test"})
        assert articles == []


# ---------------------------------------------------------------------------
# Normalize registry
# ---------------------------------------------------------------------------


class TestNormalizeRegistry:
    def test_basic(self):
        raw = {
            "FRA": [
                {"publication_name": "Le Monde", "publication_rss_feed_uri": "https://lemonde.fr/rss"},
                {"publication_name": "Libération", "publication_rss_feed_uri": "https://libe.fr/rss"},
            ],
            "USA": [
                {"publication_name": "NYT", "publication_rss_feed_uri": "https://nyt.com/rss"},
            ],
        }
        result = news_grab._normalize_registry(raw)
        assert "France" in result
        assert "United States" in result
        assert len(result["France"]) == 2
        assert result["France"][0]["name"] == "Le Monde"

    def test_skips_empty_url(self):
        raw = {"FRA": [{"publication_name": "Bad", "publication_rss_feed_uri": ""}]}
        result = news_grab._normalize_registry(raw)
        assert "France" not in result

    def test_unknown_iso3(self):
        raw = {"XYZ": [{"publication_name": "X", "publication_rss_feed_uri": "https://x.com/rss"}]}
        result = news_grab._normalize_registry(raw)
        assert "XYZ" in result


# ---------------------------------------------------------------------------
# Temporal filtering
# ---------------------------------------------------------------------------


class TestFilterByTime:
    def _article(self, hours_ago: int | None) -> dict:
        if hours_ago is None:
            return {"title": "no date", "published_at": None}
        dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return {"title": f"{hours_ago}h ago", "published_at": dt.isoformat()}

    def test_keeps_recent(self):
        articles = [self._article(1), self._article(5), self._article(48)]
        result = news_grab._filter_by_time(articles, 24)
        assert len(result) == 2

    def test_keeps_no_date(self):
        articles = [self._article(None)]
        result = news_grab._filter_by_time(articles, 24)
        assert len(result) == 1

    def test_zero_hours_no_filter(self):
        articles = [self._article(1000)]
        result = news_grab._filter_by_time(articles, 0)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_removes_duplicates_by_url(self):
        articles = [
            {"title": "A", "url": "https://example.com/1"},
            {"title": "B", "url": "https://example.com/1"},
            {"title": "C", "url": "https://example.com/2"},
        ]
        result = news_grab._deduplicate(articles)
        assert len(result) == 2
        assert result[0]["title"] == "A"

    def test_falls_back_to_title(self):
        articles = [
            {"title": "Same Title", "url": ""},
            {"title": "Same Title", "url": ""},
        ]
        result = news_grab._deduplicate(articles)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    def test_clears_memory_cache(self):
        news_grab._memory_cache = {"France": []}
        news_grab._memory_cache_ts = 999.0
        news_grab._memory_cache_remote_sha = "abc"
        news_grab.invalidate_cache()
        assert news_grab._memory_cache is None
        assert news_grab._memory_cache_ts == 0.0
        assert news_grab._memory_cache_remote_sha is None


# ---------------------------------------------------------------------------
# Force refresh env var
# ---------------------------------------------------------------------------


class TestForceRefresh:
    def test_enabled(self):
        with patch.dict("os.environ", {"NEWS_FEED_BYPASS_CACHE": "true"}):
            assert news_grab._force_refresh_enabled() is True

    def test_disabled(self):
        with patch.dict("os.environ", {"NEWS_FEED_BYPASS_CACHE": ""}):
            assert news_grab._force_refresh_enabled() is False

    def test_not_set(self):
        with patch.dict("os.environ", {}, clear=True):
            assert news_grab._force_refresh_enabled() is False
