# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A news feed collection tool ("Hermes") that fetches articles from 1100+ RSS feeds across 150+ countries. The feed registry is sourced from the `cyberbobjr/news-feed-list-of-countries` GitHub repository and cached locally for 24 hours (with SHA-based invalidation).

**Design principle:** the tool **collects**, the agent **thinks**. Classification, summarization, translation, and formatting are the agent's job — not this tool's.

## Architecture

Single-file tool (`server.py`) with these layers:

1. **Registry loading** — Three-tier cache: in-memory → disk (`.cache/`) → remote fetch. Computes SHA-1 of the downloaded JSON to detect upstream changes.
2. **Country resolution** — Accepts ISO 3166-1 alpha-3 codes, English names, French aliases, and fuzzy prefix matching. Maps through `_ISO3_TO_NAME` / `_NAME_TO_ISO3` dicts.
3. **RSS parsing** — Stdlib `xml.etree.ElementTree`, handles both RSS 2.0 (`<item>`) and Atom (`<entry>`) feeds. No external XML dependency.
4. **Concurrent fetching** — `httpx.AsyncClient` with semaphore-bounded concurrency (12 max). Each feed has a 15s timeout.
5. **Post-processing** — Time-window filtering, URL-based deduplication, recency sort.
6. **Registration** — Registers as MCP tool via `FastMCP`.

## Dependencies

- `httpx` — async HTTP client (only external runtime dependency)
- `mcp` — Model Context Protocol SDK

## Environment Variables

- `NEWS_FEEDS_JSON_URL` — override the feeds registry URL (default: raw GitHub URL from `cyberbobjr/news-feed-list-of-countries`)
- `NEWS_FEED_BYPASS_CACHE` — set to `1`/`true` to skip cache
