# MCP News Feeds

An MCP server that collects articles from over 1100 RSS feeds distributed across 150+ countries, sourced from the community registry [news-feed-list-of-countries](https://github.com/cyberbobjr/news-feed-list-of-countries).

## Installation

### 1. Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Starting the MCP Server

```bash
python news_grab.py
```

The server runs on `stdio` and exposes 3 tools:

| Tool | Description |
|------|-------------|
| `news_feed` | Retrieves recent articles, filterable by country, time window, and limit |
| `news_feed_countries` | Lists all available countries with the number of feeds per country |
| `news_feed_invalidate_cache` | Clears the registry cache to force a reload |

### Configuration with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "news-feeds": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/news_grab.py"]
    }
  }
}
```

Replace `/path/to/venv` with your actual venv directory path. On Windows, use: `C:\\path\\to\\venv\\Scripts\\python.exe`

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

The RSS feed registry is cached in the `.cache/` directory next to the script. The cache is valid for 24 hours and refreshes automatically when the GitHub registry is updated.

To force a refresh:

```bash
export NEWS_FEED_BYPASS_CACHE=true
```

## Testing

```bash
pip install pytest
pytest tests/
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEWS_FEED_BYPASS_CACHE` | Set to `true` to ignore cache and always re-download the registry |
| `GITHUB_TOKEN` | Optional GitHub token to avoid rate-limiting on the API |
