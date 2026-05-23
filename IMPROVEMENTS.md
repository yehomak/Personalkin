# Improvements & Known Issues

Observed from actual usage of the MCP tools.

## SpendWisely

**WAL file risk** (medium)
When the Docker volume was migrated to a bind mount, both `spendwisely.duckdb` and `spendwisely.duckdb.wal` were copied. The WAL means the DB wasn't checkpointed — MCP reads may miss recent transactions until the SpendWisely backend opens the DB in write mode and flushes it. Run `docker compose up` once to trigger a checkpoint.

**May income = 0** (medium)
Suspicious for mid-month. Either salary hasn't arrived yet or the USD salary attribution broke. Check `_salary_month()` logic in SpendWisely parser.

**USD amounts in PLN summaries** (low)
`get_spending_summary` sums `abs_amount` assuming PLN. USD transactions are included with their bank-converted PLN equivalent — works today but fragile if currency handling in SpendWisely changes.

---

## MyCalendar

**Times shown in UTC, not local** (high)
`_fmt()` in `tools/calendar.py` returns raw UTC time. Every time displayed is 2 hours behind Warsaw local time in summer (CEST = UTC+2). Fix: convert to `Europe/Warsaw` before formatting.

**No look-back tool** (medium)
`get_upcoming_events` and `get_events_on_date` only work forward or on a specific known date. Can't ask "what did I do last week?" without knowing exact dates. Add `get_past_events(days)`.

**Recurring events not flagged** (low)
Events with a `recurrenceRule` look identical to one-off events in tool output. Should surface a `recurring: true` field so the AI can reason about habits vs. one-time entries.
