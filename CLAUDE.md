# Personalkin

MCP server exposing personal data to Claude Code. Python + FastMCP.

## Structure

- `server.py` — registers all tools with FastMCP
- `tools/spending.py` — DuckDB queries against SpendWisely
- `tools/calendar.py` — MongoDB queries against MyCalendar

## Adding a tool

1. Write a plain function in the relevant `tools/*.py` file
2. Register it in `server.py` with `mcp.tool()(fn)`
3. Test the function directly (`python -c "from tools.x import fn; print(fn())"`)
4. Restart Claude Code

## Credentials

Never in source. Always in the `env` block of the MCP server config in `~/.claude.json`.

## Data sources

- SpendWisely DB: `~/Projects/SpendWisely/db/spendwisely.duckdb` (local DuckDB, read-only)
- MyCalendar: MongoDB Atlas `mycalendar` db — collections: `events`, `categories`
