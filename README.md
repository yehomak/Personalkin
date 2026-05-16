# Personalkin

Personal AI assistant MCP server. Connects spending and calendar data into Claude Code via natural language.

## Tools

**Spending** (reads SpendWisely's DuckDB)
- `get_spending_summary(months)` — income/expenses/net by month
- `get_spending_by_category(months, direction)` — category breakdown
- `get_recent_transactions(limit, category, direction)` — filtered transaction list

**Calendar** (reads MyCalendar's MongoDB)
- `get_upcoming_events(days)` — next N days in chronological order
- `get_events_on_date(date)` — all events on a specific date

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Add to `~/.claude.json` under `mcpServers`:

```json
"personalkin": {
  "type": "stdio",
  "command": "/path/to/Personalkin/.venv/bin/python",
  "args": ["/path/to/Personalkin/server.py"],
  "env": {
    "SPENDWISELY_DB": "/path/to/SpendWisely/db/spendwisely.duckdb",
    "MYCALENDAR_MONGO_URI": "mongodb+srv://..."
  }
}
```

## Data sources

- SpendWisely DuckDB — local file, read-only
- MyCalendar MongoDB Atlas — cloud, read-only
