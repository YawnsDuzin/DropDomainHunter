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
| `main.py` | Entry point, APScheduler orchestration, signal handling, `reload_scheduler()` |
| `config.py` | Pydantic settings from `.env`, domain filters, scoring thresholds |
| `crawler/expired_domains.py` | HTTP client with login, retry logic (tenacity), rate limiting |
| `crawler/parser.py` | HTML parsing with multi-strategy fallback, smart keyword matching |
| `crawler/anti_blocking.py` | User-Agent rotation, adaptive delay, proxy rotation, human behavior |
| `crawler/state.py` | Global crawl state tracking (progress, status, elapsed time) |
| `checker/availability.py` | Domain availability check via RDAP/WHOIS protocols |
| `checker/history.py` | Domain history via Archive.org Wayback Machine |
| `scorer/evaluator.py` | Composite scoring, value estimation by score tier |
| `scorer/length.py`, `keyword.py`, `pattern.py` | Individual scoring algorithms |
| `database/models.py` | Domain, WatchlistItem, CrawlLog dataclasses + Database class |
| `notifier/manager.py` | Unified notification dispatch |
| `notifier/priority.py` | Alert prioritization (CRITICAL/HIGH/MEDIUM/LOW/BATCH) |
| `notifier/telegram_bot.py` | Telegram callback handlers and bot commands |
| `web/app.py` | FastAPI dashboard with Jinja2 templates, runtime settings API |
| `web/auth.py` | HTTP Basic Auth and session-based authentication |

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

### Static Configuration (`.env`)
- `EXPIRED_DOMAINS_USERNAME/PASSWORD`: Required for authenticated crawling
- `TELEGRAM_BOT_TOKEN/CHAT_ID`: Telegram notifications
- `DISCORD_WEBHOOK_URL`: Discord notifications
- `PROGRAM_NAME/PROGRAM_VERSION`: Program identity
- `WEB_USERNAME/WEB_PASSWORD`: Web dashboard authentication
- `USE_PROXY/PROXY_LIST`: Proxy rotation settings
- `CHECK_AVAILABILITY/CHECK_HISTORY`: Domain verification toggles

### Runtime Configuration (`data/runtime_settings.json`)
Managed via web dashboard, hot-reloadable:
- Crawl schedules (full/week/day enabled, times, intervals)
- Domain filters (length, TLDs, numbers, hyphens)
- Alert settings (min score, report time, heartbeat)
- Log level

### Custom Keywords (`data/keywords.json`)
```json
{"keyword": {"score": 90, "category": "TECH"}}
```
Categories: TECH, FINANCE, BUSINESS, GENERIC

## Code Patterns

- **Async context managers** for crawler/database lifecycle (`__aenter__`/`__aexit__`)
- **structlog** for structured logging throughout
- **uvloop** for async performance optimization
- **tenacity** for HTTP retry with exponential backoff
- **Dataclasses** for Domain, CrawlLog entities with `to_dict()` methods
- Web routes follow REST conventions with HTML templates and JSON API endpoints
- **Runtime settings** saved to JSON, scheduler reloaded on change (`reload_scheduler`)
- **Crawl state** tracked globally via `crawler/state.py` for real-time progress
- **Multi-strategy parsing** in `RobustParser` (class-based → structure-based → regex)
- **Adaptive delay** with exponential backoff on errors (429→3x, 403→2x)
- **RDAP/WHOIS fallback** chain for domain availability checking

## Web Dashboard

### Key Pages
- `/`: Domain list with filters, sorting, pagination, charts
- `/keywords`: Keyword management (add/edit/delete with categories)
- `/settings`: Runtime configuration (crawl schedule, filters, alerts)

### Key APIs
- `GET/POST /api/settings`: Runtime settings CRUD
- `POST /api/settings/reset`: Reset to defaults
- `GET/POST/PUT/DELETE /api/keywords`: Keyword management
- `POST /api/crawl/trigger`: Manual crawl trigger
- `GET /api/crawl/status`: Real-time crawl progress
