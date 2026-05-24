# Personalkin — Claude context

## Stack
Python 3.13, FastMCP (stdio), DuckDB (read-only), pymongo (read-only)
One MCP server, three data sources, zero writes.

## Key commands
```bash
# Test a tool directly (no server needed)
.venv/bin/python -c "from tools.spending import get_spending_summary; print(get_spending_summary(3))"
.venv/bin/python -c "from tools.calendar import get_upcoming_events; print(get_upcoming_events(7))"
.venv/bin/python -c "from tools.garmin import get_health_snapshot; print(get_health_snapshot())"

# Verify server starts cleanly
.venv/bin/python server.py
```

## Project structure
```
server.py          — FastMCP instance; registers all tools; entry point
tools/
  spending.py      — DuckDB queries against SpendWisely
  calendar.py      — MongoDB queries against MyCalendar
  garmin.py        — DuckDB queries against Garmin + reads generated report files
scripts/
  generate_profile.py        — writes context/health/profile.md (health reference doc)
  generate_report.py         — writes context/health/reports/YYYY-WXX.md (weekly)
  generate_monthly_report.py — writes context/health/reports/YYYY-MM.md (monthly)
  generate_activities.py     — writes context/health/activities/YYYY-MM-DD-type.md per session
  run_daily.py               — launchd wrapper: sync + activities + macOS notification (tap-to-open weekly report)
  run_weekly.py              — launchd wrapper: sync + prev-week report + clickable notification
  run_monthly.py             — launchd wrapper: prev-month report + clickable notification
requirements.txt   — mcp, duckdb, pymongo[srv]
.venv/             — gitignored; install with: pip install -r requirements.txt
```

## Key files
- `server.py` — read before adding any tool; registration pattern is `mcp.tool()(fn)`
- `tools/spending.py` — `_conn()` opens DuckDB read-only; `_start_month(n)` computes YYYY-MM N months back
- `tools/calendar.py` — `_db()` is a MongoClient singleton; `_category_map()` resolves categoryId → name
- `tools/garmin.py` — `_conn()` opens Garmin DuckDB read-only; `HEALTH_DIR` points to `context/health/`

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
- `GARMIN_DB` — absolute path to `garmin.duckdb` (lives in `~/Projects/garmin-sync/`)

All three are set in the `env` block of the `personalkin` entry in `~/.claude.json`. Never default them in code.
`GARMIN_DB` is also passed as an env var to the launchd runner scripts via `ENV = {**os.environ, "GARMIN_DB": GARMIN_DB}`.
Missing `GARMIN_DB` raises `RuntimeError` immediately — no silent fallback.

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

**Garmin (DuckDB — garmin.duckdb, read-only)**
```
health_days:       date, steps, step_goal, floors_up, distance_km,
                   calories_total, calories_active, calories_bmr,
                   hr_min, hr_max, rhr, stress_avg,
                   bb_max, bb_min, bb_end,
                   moderate_activity_min, vigorous_activity_min,
                   sleep_start, sleep_end, sleep_score, sleep_qualifier,
                   sleep_total_min, sleep_deep_min, sleep_light_min,
                   sleep_rem_min, sleep_awake_min, sleep_spo2_avg, sleep_rr_avg,
                   hrv_weekly_avg, hrv_last_night, hrv_baseline_low, hrv_baseline_high,
                   hrv_status, spo2_avg, spo2_min, rr_waking_avg,
                   training_readiness_score, training_readiness_level,
                   recovery_time_hours, endurance_score, fitness_age

health_activities: date, type, duration_min, distance_km, avg_hr, max_hr,
                   calories, training_load, aerobic_te, anaerobic_te,
                   avg_pace_min_km, hr_zone_1_min … hr_zone_5_min
```
Populated by `~/Projects/garmin-sync/sync.py` (separate repo, own venv).

## Data sources
- SpendWisely DuckDB: `~/Projects/SpendWisely/db/spendwisely.duckdb`
  - Populated via SpendWisely's Docker backend (`docker compose up` in that repo)
  - docker-compose mounts `./db:/data` so the file is accessible from host
- MyCalendar MongoDB: Atlas cluster, db `mycalendar`
  - Always available (cloud); no local service needed
- Garmin DuckDB: `~/Projects/garmin-sync/garmin.duckdb`
  - Populated by `garmin-sync` repo's `sync.py` (separate venv at `~/Projects/garmin-sync/.venv`)
  - Run manually or via launchd (daily `run_daily.py`, weekly `run_weekly.py`)

## launchd automation (scripts/)
Three scripts run on schedule via launchd — fires on wake if Mac was asleep at scheduled time:
```
~/Library/LaunchAgents/com.personalkin.daily.plist   — Tue–Sun 10am: sync + notify
~/Library/LaunchAgents/com.personalkin.weekly.plist  — Mon 10am: sync + prev-week report + notify
~/Library/LaunchAgents/com.personalkin.monthly.plist — 1st 10am: prev-month report + notify
```
All three send macOS notifications via `/opt/homebrew/bin/terminal-notifier` (hardcoded — launchd has minimal PATH).
All notifications are tap-to-open: daily opens the latest weekly report, weekly/monthly open their generated file.
Logs land in `/tmp/garmin-{daily,weekly,monthly}.log`.

Manage with:
```bash
launchctl load   ~/Library/LaunchAgents/com.personalkin.daily.plist   # activate
launchctl unload ~/Library/LaunchAgents/com.personalkin.daily.plist   # deactivate
launchctl list | grep personalkin                                      # check status
```

## Generated report files
```
context/health/
  profile.md                    — comprehensive health reference (run generate_profile.py)
  reports/
    YYYY-WXX.md                 — weekly report (generated every Monday)
    YYYY-MM.md                  — monthly report (generated 1st of following month)
  activities/
    YYYY-MM-DD-type.md          — one file per activity session
```
MCP tools `get_health_profile`, `get_latest_health_report`, `get_latest_monthly_report`,
and `get_activity_report(date)` read these files on demand.
Weekly glob: `????-W??.md`; monthly glob: `????-??.md` (distinct patterns, no collision).

## Gmail (claude.ai MCP — not part of this server)
Gmail is connected via the built-in Claude Code `claude.ai Gmail` MCP, not built into personalkin.
Authenticate with `/mcp` → select "claude.ai Gmail" if the session is new.

Available tools (load with ToolSearch): `search_threads`, `get_thread`, `list_labels`, `label_thread`

Use alongside spending tools to cross-reference receipts, booking confirmations, and invoices.
Useful patterns:
- Find flight bookings: `from:wizzair` or `from:ryanair` with a date range
- PAYPRO S.A. in DuckDB = WizzAir/flight payment processor — often miscategorized as Online Shopping
- Match invoice dates to DuckDB `booking_date` to confirm which charge belongs to which booking
