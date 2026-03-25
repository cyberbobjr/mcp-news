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

The server runs on `stdio` and exposes 6 tools:

| Tool | Description |
|------|-------------|
| `news_feed` | Retrieves recent articles, filterable by country, time window, and limit |
| `news_fetch_article` | Returns the full, untruncated description of a specific article |
| `news_feed_countries` | Lists all available countries with the number of feeds per country |
| `news_feed_health` | Shows feed reliability stats: healthy, unhealthy, and dead feeds |
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

**Get the full description of an article:**
```json
{
  "name": "news_fetch_article",
  "arguments": {
    "url": "https://example.com/article/123"
  }
}
```

**Check feed health for a country:**
```json
{
  "name": "news_feed_health",
  "arguments": {
    "country": "France"
  }
}
```

**List available countries:**
```json
{
  "name": "news_feed_countries"
}
```

## Response Truncation

Responses are automatically truncated to fit MCP client limits (~40,000 characters). When the payload is too large, descriptions are progressively shortened, then articles are dropped from the tail. Use `news_fetch_article` to retrieve the full description of a specific article.

## Feed Health Tracking

The server tracks the success/failure history of each feed in `~/.mcp-news/feed_health.json`. Feeds with 10 or more consecutive errors are automatically skipped during collection. Use the `news_feed_health` tool to inspect feed reliability.

## Cache

The RSS feed registry is cached in `~/.mcp-news/cache/`. The cache is valid for 24 hours and refreshes automatically when the remote registry changes (SHA-1 comparison).

To force a refresh:

```bash
export NEWS_FEED_BYPASS_CACHE=true
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--verbose` | Enable verbose logging and write fetched articles to `~/.mcp-news/logs/` as timestamped JSON files |

Example with verbose mode:

```json
{
  "mcpServers": {
    "news-feeds": {
      "command": "uvx",
      "args": ["mcp-news", "--verbose"]
    }
  }
}
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
| `MCP_NEWS_DATA_DIR` | Override the data directory (default: `~/.mcp-news`) |
