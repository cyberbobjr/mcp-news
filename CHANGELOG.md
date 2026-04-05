# Changelog

## [1.1.2] - 2026-04-04

### Bug Fixes
- `news_feed`: `countries` is now a required parameter — calling it without a country list caused stdio timeouts by attempting to fetch all 1100+ feeds simultaneously. An empty or missing `countries` now returns an actionable error guiding the LLM to call `news_feed_countries` first, then retry with a specific list.
- Add a 45s global timeout (`_FETCH_ALL_TIMEOUT`) as a safety net for large country lists.

## [1.1.1] - 2026-03-25

### Bug Fixes
- update repository URL in pyproject.toml (a351f55)

### Features
- add feed health tracking and article fetch tools (ed865bd)
- add verbose logging, response truncation, and configurable data dir (45f4b5a)
- add tests, README, and minor fixes (cdcf548)
- add news feed collection MCP tool (2c9e698)

### Refactoring
- restructure as installable Python package (e656066)

### Chores
- bump version to 1.0.0 and mark as production/stable (ad0bc75)

### Other
- Initial commit (06a13e6)
