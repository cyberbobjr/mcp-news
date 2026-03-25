# MCP News Feeds

An MCP server that collects articles from over 1100 RSS feeds distributed across 150+ countries, sourced from the community registry [news-feed-list-of-countries](https://github.com/cyberbobjr/news-feed-list-of-countries).

## Quick Start (uvx)

No installation needed — just configure your MCP client:

```json
{
  "mcpServers": {
    "news-feeds": {
      "command": "uvx",
      "args": ["mcp-news"]
    }
  }
}
```

`uvx` will automatically download and run the server.

## Installation from source

```bash
git clone https://github.com/benjaminmarchand/mcp-news.git
cd mcp-news
pip install -e .
```

Then configure your MCP client:

```json
{
  "mcpServers": {
    "news-feeds": {
      "command": "mcp-news"
    }
  }
}
```

## Usage

The server runs on `stdio` and exposes 3 tools:

| Tool | Description |
|------|-------------|
| `news_feed` | Retrieves recent articles, filterable by country, time window, and limit |
| `news_feed_countries` | Lists all available countries with the number of feeds per country |
| `news_feed_invalidate_cache` | Clears the registry cache to force a reload |

### Example Calls

**Retrieve French news from the last 12 hours:**
```json
{
  "name": "news_feed",
  "arguments": {
    "countries": ["France"],
    "hours": 12,
    "limit": 50
  }
}
```

**List available countries:**
```json
{
  "name": "news_feed_countries"
}
```

## Cache

The RSS feed registry is cached locally. The cache is valid for 24 hours and refreshes automatically when the remote registry changes (SHA-1 comparison).

To force a refresh:

```bash
export NEWS_FEED_BYPASS_CACHE=true
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEWS_FEEDS_JSON_URL` | Override the feeds registry URL (default: raw GitHub URL from `cyberbobjr/news-feed-list-of-countries`) |
| `NEWS_FEED_BYPASS_CACHE` | Set to `true` to ignore cache and always re-download the registry |
