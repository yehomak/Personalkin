# Personalkin — Claude context

## Stack
Python 3.13, FastMCP (stdio), DuckDB (read-only), pymongo (read-only)
One MCP server, two data sources, zero writes.

## Key commands
```bash
# Test a tool directly (no server needed)
.venv/bin/python -c "from tools.spending import get_spending_summary; print(get_spending_summary(3))"
.venv/bin/python -c "from tools.calendar import get_upcoming_events; print(get_upcoming_events(7))"

# Verify server starts cleanly
.venv/bin/python server.py
```

## Project structure
```
server.py          — FastMCP instance; registers all tools; entry point
tools/
  spending.py      — DuckDB queries against SpendWisely
  calendar.py      — MongoDB queries against MyCalendar
requirements.txt   — mcp, duckdb, pymongo[srv]
.venv/             — gitignored; install with: pip install -r requirements.txt
```

## Key files
- `server.py` — read before adding any tool; registration pattern is `mcp.tool()(fn)`
- `tools/spending.py` — `_conn()` opens DuckDB read-only; `_start_month(n)` computes YYYY-MM N months back
- `tools/calendar.py` — `_db()` is a MongoClient singleton; `_category_map()` resolves categoryId → name

## Adding a tool
1. Write a plain function in the relevant `tools/*.py` — no MCP imports needed
2. Register in `server.py`: `mcp.tool()(fn)`
3. Test directly: `.venv/bin/python -c "from tools.x import fn; print(fn())"`
4. Restart Claude Code to reload the server

## Conventions
- All tools are **read-only** — no inserts, updates, or deletes ever
- **No credentials in source** — env vars only, configured in `~/.claude.json` MCP server `env` block
- Calendar times are **UTC strings** — MyCalendar stores `startAt`/`endAt` as ISO UTC; format for display with `_fmt()`
- DuckDB `direction` values: `expense`, `income`, `internal` — always exclude `internal` from spend calculations
- `month` column in DuckDB is `YYYY-MM` string — safe to filter with string comparison
- pymongo singleton in `_client` — one connection reused across tool calls in a server session

## Credentials (env vars)
- `SPENDWISELY_DB` — absolute path to `spendwisely.duckdb` (lives in `~/Projects/SpendWisely/db/`)
- `MYCALENDAR_MONGO_URI` — MongoDB Atlas SRV connection string

Both are set in the `env` block of the `personalkin` entry in `~/.claude.json`. Never default them in code.

## DB schemas

**SpendWisely (DuckDB)**
```
transactions:    id, booking_date, value_date, month (YYYY-MM), counterparty, title,
                 amount, abs_amount, currency, direction, category, bank_category,
                 operation_type, is_internal, source_file, imported_at
category_rules:  id, category, pattern, fields[], priority, comment
```

**MyCalendar (MongoDB — db: mycalendar)**
```
events:      id (uuid), userId, title, startAt (ISO UTC), endAt (ISO UTC),
             allDay, categoryId, recurrenceRule, color, googleEventId?, pendingSync?
categories:  id (uuid), userId, name, color, icon, type
```
Single userId across all documents — no need to filter by userId in MCP tools.

## Data sources
- SpendWisely DuckDB: `~/Projects/SpendWisely/db/spendwisely.duckdb`
  - Populated via SpendWisely's Docker backend (`docker compose up` in that repo)
  - docker-compose mounts `./db:/data` so the file is accessible from host
- MyCalendar MongoDB: Atlas cluster, db `mycalendar`
  - Always available (cloud); no local service needed
