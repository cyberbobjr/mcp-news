# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A news feed collection tool ("Hermes") that fetches articles from 1100+ RSS feeds across 150+ countries. The feed registry is sourced from the `cyberbobjr/news-feed-list-of-countries` GitHub repository and cached locally for 24 hours (with SHA-based invalidation).

**Design principle:** the tool **collects**, the agent **thinks**. Classification, summarization, translation, and formatting are the agent's job — not this tool's.

## Architecture

Single-file tool (`news_grab.py`) with these layers:

1. **Registry loading** — Three-tier cache: in-memory → disk (`~/.hermes/cache/`) → remote GitHub fetch. Uses GitHub Contents API SHA to detect upstream changes before TTL expires.
2. **Country resolution** — Accepts ISO 3166-1 alpha-3 codes, English names, French aliases, and fuzzy prefix matching. Maps through `_ISO3_TO_NAME` / `_NAME_TO_ISO3` dicts.
3. **RSS parsing** — Stdlib `xml.etree.ElementTree`, handles both RSS 2.0 (`<item>`) and Atom (`<entry>`) feeds. No external XML dependency.
4. **Concurrent fetching** — `httpx.AsyncClient` with semaphore-bounded concurrency (12 max). Each feed has a 15s timeout.
5. **Post-processing** — Time-window filtering, URL-based deduplication, recency sort.
6. **Registration** — Registers as `news_feed` tool in the `web` toolset via `tools.registry.registry`.

## Dependencies

- `httpx` — async HTTP client (only external runtime dependency)
- `tools.registry` — internal tool registry (imported as `from tools.registry import registry`)

## Environment Variables

- `HERMES_CACHE_DIR` — override cache directory (default: `~/.hermes/cache/`)
- `HERMES_NEWS_FEED_BYPASS_CACHE` — set to `1`/`true` to skip cache
- `GITHUB_TOKEN` — optional, used for GitHub API calls to avoid rate limits

## Known Issues

- `_write_cache_meta` and `_read_cache_meta` and `_fetch_remote_registry_sha` are each defined twice (duplicate function definitions at lines 193-211 and 240-258, and lines 214-227 and 261-274)
