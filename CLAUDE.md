# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Domain Sniper is a lightweight domain sniping system designed for 24/7 operation on Raspberry Pi 4. It automatically detects high-value expiring domains from expireddomains.net, evaluates their value using a scoring algorithm, and sends notifications via Telegram/Discord.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run full service (scheduler + web dashboard)
python main.py

# Run immediate crawl only
python main.py --crawl-now

# Run web dashboard only
python main.py --web-only

# Test configuration
python config.py

# Test evaluator
python scorer/evaluator.py

# Test crawler (mock mode)
python crawler/expired_domains.py
```

## Architecture

### Core Flow
1. **Crawling**: `ExpiredDomainsCrawler` fetches domains from expireddomains.net using httpx with session/cookie management for authenticated access
2. **Parsing**: `DomainParser` extracts domain data from HTML tables using BeautifulSoup
3. **Evaluation**: `DomainEvaluator` scores domains using weighted formula: `Length(35%) + Keyword(40%) + Pattern(25%)`
4. **Storage**: Async SQLite via aiosqlite with WAL mode for concurrent access
5. **Notification**: `NotificationManager` dispatches alerts to Telegram/Discord

### Key Components

| Module | Purpose |
|--------|---------|
| `main.py` | Entry point, APScheduler orchestration, signal handling |
| `config.py` | Pydantic settings from `.env`, domain filters, scoring thresholds |
| `crawler/expired_domains.py` | HTTP client with login, retry logic (tenacity), rate limiting |
| `crawler/parser.py` | HTML parsing, domain validation, adult keyword filtering |
| `scorer/evaluator.py` | Composite scoring, value estimation by score tier |
| `scorer/length.py`, `keyword.py`, `pattern.py` | Individual scoring algorithms |
| `database/models.py` | Domain, WatchlistItem, CrawlLog dataclasses + Database class |
| `notifier/manager.py` | Unified notification dispatch |
| `web/app.py` | FastAPI dashboard with Jinja2 templates |

### Scheduler Jobs (APScheduler)
- **full_crawl**: Daily at 06:00, all TLDs, 30-day expiry window
- **week_crawl**: Every 3 hours, 7-day expiry window
- **day_crawl**: Every 30 minutes, pending delete domains
- **daily_report**: Configurable time (default 08:00)

### Database Schema (SQLite)
- `domains`: Main table with scores, expiry dates, notification status
- `watchlist`: User-saved domains with priority
- `crawl_logs`: Crawling history and statistics
- `settings`: Key-value configuration store
- `keywords`: Custom scoring keywords

## Configuration

Environment variables loaded from `.env`:
- `EXPIRED_DOMAINS_USERNAME/PASSWORD`: Required for authenticated crawling
- `TELEGRAM_BOT_TOKEN/CHAT_ID`: Telegram notifications
- `DISCORD_WEBHOOK_URL`: Discord notifications
- `MIN_SCORE_ALERT`: Threshold for notifications (default 70)
- `MIN/MAX_DOMAIN_LENGTH`, `ALLOWED_TLDS`, `ALLOW_NUMBERS`, `ALLOW_HYPHENS`: Domain filters

## Code Patterns

- **Async context managers** for crawler/database lifecycle (`__aenter__`/`__aexit__`)
- **structlog** for structured logging throughout
- **uvloop** for async performance optimization
- **tenacity** for HTTP retry with exponential backoff
- **Dataclasses** for Domain, CrawlLog entities with `to_dict()` methods
- Web routes follow REST conventions with HTML templates and JSON API endpoints
