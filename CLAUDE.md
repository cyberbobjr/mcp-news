# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A news feed collection MCP server that fetches articles from 1100+ RSS feeds across 150+ countries. The feed registry is sourced from the `cyberbobjr/news-feed-list-of-countries` GitHub repository and cached locally for 24 hours (with SHA-1 invalidation).

**Design principle:** the tool **collects**, the agent **thinks**. Classification, summarization, translation, and formatting are the agent's job — not this tool's.

## Architecture

Single-file MCP server (`src/mcp_news/server.py`) with these layers:

1. **Registry loading** — Three-tier cache: in-memory → disk (`~/.mcp-news/cache/`) → remote fetch. Computes SHA-1 of the downloaded JSON to detect upstream changes.
2. **Country resolution** — Accepts ISO 3166-1 alpha-3 codes, English names, French aliases, and fuzzy prefix matching. Maps through `_ISO3_TO_NAME` / `_NAME_TO_ISO3` dicts.
3. **RSS parsing** — Stdlib `xml.etree.ElementTree`, handles both RSS 2.0 (`<item>`) and Atom (`<entry>`) feeds. No external XML dependency.
4. **Concurrent fetching** — `httpx.AsyncClient` with semaphore-bounded concurrency (12 max). Each feed has a 15s timeout.
5. **Post-processing** — Time-window filtering, URL-based deduplication, recency sort.
6. **Response truncation** — `_truncate_to_fit()` progressively shortens descriptions then drops articles to stay under 40k chars.
7. **Feed health tracking** — Persists per-feed success/error counts in `~/.mcp-news/feed_health.json`. Feeds with 10+ consecutive errors are automatically skipped.

## MCP Tools

| Tool | Description |
|------|-------------|
| `news_feed` | Fetch recent articles, filterable by country, time window, and limit |
| `news_fetch_article` | Return the full untruncated description of a specific article |
| `news_feed_countries` | List all available countries with feed counts |
| `news_feed_health` | Show feed reliability stats (healthy/unhealthy/dead), filtrable by country |
| `news_feed_invalidate_cache` | Clear the registry cache |

## Dependencies

- `httpx` — async HTTP client (only external runtime dependency)
- `mcp` — Model Context Protocol SDK

## Command-Line Options

- `--verbose` — enable debug logging and write fetched articles to `~/.mcp-news/logs/`

## Environment Variables

- `NEWS_FEEDS_JSON_URL` — override the feeds registry URL (default: raw GitHub URL from `cyberbobjr/news-feed-list-of-countries`)
- `NEWS_FEED_BYPASS_CACHE` — set to `1`/`true` to skip cache
- `MCP_NEWS_DATA_DIR` — override the data directory (default: `~/.mcp-news`)

## Data Directory (`~/.mcp-news/`)

- `cache/` — registry cache (JSON + meta with SHA)
- `logs/` — verbose mode article dumps (timestamped JSON)
- `feed_health.json` — per-feed success/error tracking
