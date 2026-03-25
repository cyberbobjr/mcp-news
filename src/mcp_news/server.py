#!/usr/bin/env python3
"""MCP server for news feed collection.

Fetches articles from RSS feeds sourced from the community-maintained
``news-feed-list-of-countries`` GitHub repository.  The feed registry is
fetched once and cached locally for 24 hours.

Design principle: the tool **collects**, the agent **thinks**.
Classification, summarization, translation, and formatting are the agent's job.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("news-feeds")

# ---------------------------------------------------------------------------
# Remote source registry (GitHub JSON) with local file cache
# ---------------------------------------------------------------------------

_DEFAULT_FEEDS_JSON_URL = (
    "https://raw.githubusercontent.com/cyberbobjr/news-feed-list-of-countries"
    "/master/active-feeds-auto-generated.json"
)


def _feeds_json_url() -> str:
    return os.environ.get("NEWS_FEEDS_JSON_URL", "").strip() or _DEFAULT_FEEDS_JSON_URL

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
_CACHE_FILE = _CACHE_DIR / "news_feeds_registry.json"
_CACHE_META_FILE = _CACHE_DIR / "news_feeds_registry.meta.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# In-memory cache (avoids re-reading the file on every call within a session)
_memory_cache: Optional[Dict[str, List[Dict[str, str]]]] = None
_memory_cache_ts: float = 0.0
_memory_cache_remote_sha: Optional[str] = None


def invalidate_cache() -> None:
    """Invalidate both in-memory and on-disk registry caches."""
    global _memory_cache, _memory_cache_ts, _memory_cache_remote_sha
    _memory_cache = None
    _memory_cache_ts = 0.0
    _memory_cache_remote_sha = None
    try:
        if _CACHE_FILE.exists():
            _CACHE_FILE.unlink()
        if _CACHE_META_FILE.exists():
            _CACHE_META_FILE.unlink()
    except Exception as exc:
        logger.debug("news_feed: cache invalidation error: %s", exc)


def _force_refresh_enabled() -> bool:
    """Return True when cache bypass is explicitly requested."""
    return os.environ.get("NEWS_FEED_BYPASS_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}

# ---------------------------------------------------------------------------
# ISO 3166-1 alpha-3 → human-readable country name
# ---------------------------------------------------------------------------

_ISO3_TO_NAME: Dict[str, str] = {
    "AFG": "Afghanistan", "ALB": "Albania", "DZA": "Algeria", "AND": "Andorra",
    "ARG": "Argentina", "ARM": "Armenia", "AUS": "Australia", "AUT": "Austria",
    "AZE": "Azerbaijan", "BHS": "Bahamas", "BGD": "Bangladesh", "BRB": "Barbados",
    "BLR": "Belarus", "BEL": "Belgium", "BLZ": "Belize", "BEN": "Benin",
    "BMU": "Bermuda", "BOL": "Bolivia", "BIH": "Bosnia and Herzegovina",
    "BRA": "Brazil", "BGR": "Bulgaria", "BDI": "Burundi", "KHM": "Cambodia",
    "CMR": "Cameroon", "CAN": "Canada", "CYM": "Cayman Islands", "CHL": "Chile",
    "CHN": "China", "COL": "Colombia", "CRI": "Costa Rica", "HRV": "Croatia",
    "CUB": "Cuba", "CYP": "Cyprus", "CZE": "Czech Republic", "COD": "DR Congo",
    "DNK": "Denmark", "DOM": "Dominican Republic", "ECU": "Ecuador", "EGY": "Egypt",
    "SLV": "El Salvador", "EST": "Estonia", "ETH": "Ethiopia", "FIN": "Finland",
    "FRA": "France", "GAB": "Gabon", "GEO": "Georgia", "DEU": "Germany",
    "GHA": "Ghana", "GRC": "Greece", "GTM": "Guatemala", "GIN": "Guinea",
    "HTI": "Haiti", "HND": "Honduras", "HKG": "Hong Kong", "HUN": "Hungary",
    "ISL": "Iceland", "IND": "India", "IDN": "Indonesia", "IRN": "Iran",
    "IRQ": "Iraq", "IRL": "Ireland", "ISR": "Israel", "ITA": "Italy",
    "JAM": "Jamaica", "JPN": "Japan", "JOR": "Jordan", "KAZ": "Kazakhstan",
    "KEN": "Kenya", "PRK": "North Korea", "KOR": "South Korea", "KWT": "Kuwait",
    "KGZ": "Kyrgyzstan", "LVA": "Latvia", "LBN": "Lebanon", "LBY": "Libya",
    "LTU": "Lithuania", "LUX": "Luxembourg", "MKD": "North Macedonia",
    "MDG": "Madagascar", "MYS": "Malaysia", "MLI": "Mali", "MLT": "Malta",
    "MRT": "Mauritania", "MUS": "Mauritius", "MEX": "Mexico", "MDA": "Moldova",
    "MCO": "Monaco", "MNG": "Mongolia", "MNE": "Montenegro", "MAR": "Morocco",
    "MOZ": "Mozambique", "MMR": "Myanmar", "NAM": "Namibia", "NPL": "Nepal",
    "NLD": "Netherlands", "NZL": "New Zealand", "NIC": "Nicaragua", "NER": "Niger",
    "NGA": "Nigeria", "NOR": "Norway", "OMN": "Oman", "PAK": "Pakistan",
    "PAN": "Panama", "PRY": "Paraguay", "PER": "Peru", "PHL": "Philippines",
    "POL": "Poland", "PRT": "Portugal", "QAT": "Qatar", "ROU": "Romania",
    "RUS": "Russia", "RWA": "Rwanda", "SAU": "Saudi Arabia", "SEN": "Senegal",
    "SRB": "Serbia", "SGP": "Singapore", "SVK": "Slovakia", "SVN": "Slovenia",
    "SOM": "Somalia", "ZAF": "South Africa", "ESP": "Spain", "LKA": "Sri Lanka",
    "SDN": "Sudan", "SWE": "Sweden", "CHE": "Switzerland", "SYR": "Syria",
    "TWN": "Taiwan", "TJK": "Tajikistan", "TZA": "Tanzania", "THA": "Thailand",
    "TGO": "Togo", "TTO": "Trinidad and Tobago", "TUN": "Tunisia", "TUR": "Turkey",
    "UGA": "Uganda", "UKR": "Ukraine", "ARE": "United Arab Emirates",
    "GBR": "United Kingdom", "USA": "United States", "URY": "Uruguay",
    "UZB": "Uzbekistan", "VEN": "Venezuela", "VNM": "Vietnam", "YEM": "Yemen",
    "ZMB": "Zambia", "ZWE": "Zimbabwe",
}

# Reverse map: lowercase name → ISO3 code (for user input resolution)
_NAME_TO_ISO3: Dict[str, str] = {}
for _code, _name in _ISO3_TO_NAME.items():
    _NAME_TO_ISO3[_name.lower()] = _code
# Common aliases
_NAME_TO_ISO3.update({
    "usa": "USA", "us": "USA", "united states": "USA",
    "uk": "GBR", "great britain": "GBR", "britain": "GBR",
    "south korea": "KOR", "north korea": "PRK",
    "uae": "ARE", "emirates": "ARE",
    "czech republic": "CZE", "czechia": "CZE",
    "dr congo": "COD", "congo": "COD",
    "ivory coast": "CIV", "côte d'ivoire": "CIV",
    # French aliases
    "états-unis": "USA", "etats-unis": "USA", "etats unis": "USA",
    "france": "FRA", "allemagne": "DEU", "espagne": "ESP",
    "italie": "ITA", "belgique": "BEL", "suisse": "CHE",
    "russie": "RUS", "chine": "CHN", "japon": "JPN",
    "inde": "IND", "brésil": "BRA", "bresil": "BRA",
    "royaume-uni": "GBR", "royaume uni": "GBR",
    "corée du sud": "KOR", "coree du sud": "KOR",
    "arabie saoudite": "SAU", "afrique du sud": "ZAF",
})


def _resolve_country_code(user_input: str) -> Optional[str]:
    """Resolve a user-provided country name or code to an ISO3 code."""
    s = user_input.strip()
    if s.upper() in _ISO3_TO_NAME:
        return s.upper()
    code = _NAME_TO_ISO3.get(s.lower())
    if code:
        return code
    sl = s.lower()
    for name, code in _NAME_TO_ISO3.items():
        if name.startswith(sl):
            return code
    return None


# ---------------------------------------------------------------------------
# Registry loading & caching
# ---------------------------------------------------------------------------


def _cache_is_fresh() -> bool:
    if not _CACHE_FILE.exists():
        return False
    age = time.time() - _CACHE_FILE.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


def _read_cache() -> Optional[Dict[str, Any]]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.debug("news_feed: cache read error: %s", exc)
        return None


def _write_cache(data: Dict[str, Any]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("news_feed: cache write error: %s", exc)


def _write_cache_meta(remote_sha: Optional[str]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_META_FILE, "w", encoding="utf-8") as f:
            json.dump({"sha": remote_sha, "cached_at": time.time()}, f, ensure_ascii=False)
    except Exception as exc:
        logger.debug("news_feed: cache meta write error: %s", exc)


def _read_cache_meta() -> Optional[Dict[str, Any]]:
    try:
        with open(_CACHE_META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("news_feed: cache meta read error: %s", exc)
        return None


async def _fetch_registry_json() -> tuple[Dict[str, Any], str]:
    """Fetch the registry JSON and return (parsed_data, sha1_hex)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(_feeds_json_url(), follow_redirects=True)
        resp.raise_for_status()
        content_sha = hashlib.sha1(resp.content).hexdigest()
        return resp.json(), content_sha


def _normalize_registry(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    result: Dict[str, List[Dict[str, str]]] = {}
    for iso3, feeds in raw.items():
        country_name = _ISO3_TO_NAME.get(iso3, iso3)
        sources: List[Dict[str, str]] = []
        for feed in feeds:
            if not isinstance(feed, dict):
                continue
            url = feed.get("publication_rss_feed_uri", "").strip()
            name = feed.get("publication_name", "").strip()
            if url:
                sources.append({"name": name, "url": url})
        if sources:
            result[country_name] = sources
    return result


async def _load_sources() -> Dict[str, List[Dict[str, str]]]:
    global _memory_cache, _memory_cache_ts, _memory_cache_remote_sha

    force_refresh = _force_refresh_enabled()

    # 1) Memory cache — valid if TTL hasn't expired and no force refresh
    if (
        not force_refresh
        and _memory_cache is not None
        and (time.time() - _memory_cache_ts) < _CACHE_TTL_SECONDS
    ):
        return _memory_cache

    # 2) Disk cache — valid if TTL hasn't expired and no force refresh
    if (not force_refresh) and _cache_is_fresh():
        raw = _read_cache()
        if raw:
            meta = _read_cache_meta()
            cached_sha = meta.get("sha") if isinstance(meta, dict) else None
            _memory_cache = _normalize_registry(raw)
            _memory_cache_ts = time.time()
            _memory_cache_remote_sha = cached_sha
            logger.debug("news_feed: loaded %d countries from disk cache", len(_memory_cache))
            return _memory_cache

    # 3) Remote fetch — download, compute SHA, compare with cache
    try:
        raw, remote_sha = await _fetch_registry_json()

        # If disk cache exists and SHA matches, no need to rewrite
        meta = _read_cache_meta()
        cached_sha = meta.get("sha") if isinstance(meta, dict) else None
        if cached_sha == remote_sha and not force_refresh:
            cached_raw = _read_cache()
            if cached_raw:
                _memory_cache = _normalize_registry(cached_raw)
                _memory_cache_ts = time.time()
                _memory_cache_remote_sha = cached_sha
                logger.debug("news_feed: remote unchanged (SHA match), using disk cache")
                return _memory_cache

        _write_cache(raw)
        _write_cache_meta(remote_sha)
        _memory_cache = _normalize_registry(raw)
        _memory_cache_ts = time.time()
        _memory_cache_remote_sha = remote_sha
        logger.info("news_feed: fetched %d countries from remote", len(_memory_cache))
        return _memory_cache
    except Exception as exc:
        logger.error("news_feed: failed to fetch registry: %s", exc)
        raw = _read_cache()
        if raw:
            meta = _read_cache_meta()
            cached_sha = meta.get("sha") if isinstance(meta, dict) else None
            _memory_cache = _normalize_registry(raw)
            _memory_cache_ts = time.time()
            _memory_cache_remote_sha = cached_sha
            logger.info("news_feed: falling back to stale disk cache (%d countries)", len(_memory_cache))
            return _memory_cache
        return {}


# ---------------------------------------------------------------------------
# RSS parsing (stdlib xml.etree — no extra dependency)
# ---------------------------------------------------------------------------


def _parse_rss_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _clean_html_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_rss_xml(xml_bytes: bytes, source_meta: Dict[str, str]) -> List[Dict[str, Any]]:
    articles: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.debug("news_feed: XML parse error for %s: %s", source_meta.get("url"), exc)
        return []

    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
        for attr_key in list(elem.attrib):
            if "}" in attr_key:
                elem.attrib[attr_key.split("}", 1)[1]] = elem.attrib.pop(attr_key)

    items = root.findall(".//item")
    if not items:
        items = root.findall(".//entry")

    source_name = source_meta.get("name", "")
    source_url = source_meta.get("url", "")
    country = source_meta.get("country", "")

    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        if not link:
            link_elem = item.find("link")
            if link_elem is not None:
                link = (link_elem.get("href") or "").strip()
        description = (
            _text(item, "description")
            or _text(item, "summary")
            or _text(item, "content")
        )
        pub_date_str = (
            _text(item, "pubDate")
            or _text(item, "published")
            or _text(item, "updated")
        )
        pub_date = _parse_rss_date(pub_date_str)

        if not title and not link:
            continue

        articles.append({
            "title": title or "",
            "url": link or "",
            "description": _clean_html_tags(description or ""),
            "published_at": pub_date.isoformat() if pub_date else None,
            "source_name": source_name,
            "source_url": source_url,
            "country": country,
        })

    return articles


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 15.0
_MAX_CONCURRENCY = 12


async def _fetch_single_feed(
    client: httpx.AsyncClient,
    source: Dict[str, str],
    country: str,
) -> Dict[str, Any]:
    url = source.get("url", "")
    source_meta = {**source, "country": country}
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        articles = _parse_rss_xml(resp.content, source_meta)
        return {
            "source": source.get("name", url),
            "country": country,
            "url": url,
            "articles": articles,
            "error": None,
        }
    except Exception as exc:
        logger.debug("news_feed: fetch error for %s: %s", url, exc)
        return {
            "source": source.get("name", url),
            "country": country,
            "url": url,
            "articles": [],
            "error": str(exc),
        }


async def _fetch_all_feeds(
    countries: List[str],
    sources_map: Dict[str, List[Dict[str, str]]],
) -> List[Dict[str, Any]]:
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def bounded(client: httpx.AsyncClient, source: Dict[str, str], country: str):
        async with sem:
            return await _fetch_single_feed(client, source, country)

    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        headers={"User-Agent": "MCPNewsFeed/1.0"},
    ) as client:
        tasks = [
            bounded(client, source, country)
            for country in countries
            for source in sources_map.get(country, [])
        ]
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        clean: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, BaseException):
                clean.append({
                    "source": "unknown", "country": "", "url": "",
                    "articles": [], "error": str(r),
                })
            else:
                clean.append(r)  # type: ignore[arg-type]
        return clean


# ---------------------------------------------------------------------------
# Temporal filtering & deduplication
# ---------------------------------------------------------------------------


def _filter_by_time(articles: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    if hours <= 0:
        return articles
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered: List[Dict[str, Any]] = []
    for article in articles:
        pub = article.get("published_at")
        if pub is None:
            filtered.append(article)
            continue
        try:
            dt = datetime.fromisoformat(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                filtered.append(article)
        except (ValueError, TypeError):
            filtered.append(article)
    return filtered


def _deduplicate(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for article in articles:
        key = article.get("url") or article.get("title") or id(article)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def news_feed(
    countries: Optional[list[str]] = None,
    hours: int = 24,
    limit: int = 200,
) -> str:
    """Fetch recent articles from curated news sources (1100+ RSS feeds across 150+ countries).

    Returns raw articles with title, URL, description, source, and publication date.
    Use this when the user asks for world news, breaking news, daily briefing,
    headlines, or any news-related query.

    Args:
        countries: Countries to fetch news for (names or ISO 3166-1 alpha-3 codes).
            If omitted, all registered countries are used.
            Examples: ['France', 'USA', 'CHN'], ['FRA', 'GBR'].
        hours: Time window in hours (1-72). Only articles published within this
            window are returned. Default 24.
        limit: Maximum number of articles to return (1-500). Default 200.
    """
    sources_map = await _load_sources()

    if not sources_map:
        return json.dumps({
            "success": False,
            "error": "Could not load the news feed registry. Check network or cache.",
        }, ensure_ascii=False)

    available_lower = {c.lower(): c for c in sources_map}
    if countries:
        resolved: List[str] = []
        unresolved: List[str] = []
        for c in countries:
            iso3 = _resolve_country_code(c)
            if iso3:
                name = _ISO3_TO_NAME.get(iso3, iso3)
                if name in sources_map:
                    if name not in resolved:
                        resolved.append(name)
                    continue
            canonical = available_lower.get(c.strip().lower())
            if canonical:
                if canonical not in resolved:
                    resolved.append(canonical)
            else:
                unresolved.append(c.strip())
    else:
        resolved = sorted(sources_map.keys())
        unresolved = []

    feed_results = await _fetch_all_feeds(resolved, sources_map)

    all_articles: List[Dict[str, Any]] = []
    fetch_errors: List[str] = []
    sources_scraped = 0
    for result in feed_results:
        sources_scraped += 1
        if result.get("error"):
            fetch_errors.append(f"{result['source']}: {result['error']}")
        all_articles.extend(result.get("articles", []))

    all_articles = _filter_by_time(all_articles, hours)
    all_articles = _deduplicate(all_articles)

    def _sort_key(a: Dict[str, Any]):
        pub = a.get("published_at")
        if pub:
            try:
                return (0, -datetime.fromisoformat(pub).timestamp())
            except (ValueError, TypeError):
                pass
        return (1, 0.0)

    all_articles.sort(key=_sort_key)

    truncated = len(all_articles) > limit
    all_articles = all_articles[:limit]

    payload = {
        "success": True,
        "countries_requested": resolved,
        "countries_unresolved": unresolved,
        "hours": hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "registry_countries": len(sources_map),
            "registry_total_feeds": sum(len(v) for v in sources_map.values()),
            "sources_scraped": sources_scraped,
            "articles_found": len(all_articles),
            "fetch_errors_count": len(fetch_errors),
            "fetch_errors": fetch_errors[:20],
            "truncated": truncated,
            "limit": limit,
        },
        "articles": all_articles,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
async def news_feed_countries() -> str:
    """List all available countries in the news feed registry.

    Returns a JSON object with all country names and their number of feeds.
    """
    sources_map = await _load_sources()
    if not sources_map:
        return json.dumps({
            "success": False,
            "error": "Could not load the news feed registry.",
        }, ensure_ascii=False)

    countries = {name: len(feeds) for name, feeds in sorted(sources_map.items())}
    return json.dumps({
        "success": True,
        "total_countries": len(countries),
        "total_feeds": sum(countries.values()),
        "countries": countries,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def news_feed_invalidate_cache() -> str:
    """Invalidate the news feed registry cache.

    Forces a fresh download of the feed registry on the next call.
    """
    invalidate_cache()
    return json.dumps({"success": True, "message": "Cache invalidated."})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
