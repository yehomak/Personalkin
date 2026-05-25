# Improvements & Known Issues

Observed from actual usage of the MCP tools.


## MyCalendar

**Times shown in UTC, not local** (high)
`_fmt()` in `tools/calendar.py` returns raw UTC time. Displayed times are behind local time depending on timezone offset. Fix: convert UTC to local timezone before formatting (e.g. via `zoneinfo`).

**No look-back tool** (medium)
`get_upcoming_events` and `get_events_on_date` only work forward or on a specific known date. Can't ask "what did I do last week?" without knowing exact dates. Add `get_past_events(days)`.

**Recurring events not flagged** (low)
Events with a `recurrenceRule` look identical to one-off events in tool output. Should surface a `recurring: true` field so the AI can reason about habits vs. one-time entries.

---

## Notifications

**Telegram bot** (future)
Replace `terminal-notifier` with a Telegram bot for cross-platform delivery (iPhone, any device). Setup: `@BotFather` → token + `chat_id`. Extract a shared `scripts/notify.py` helper with a `notify_telegram(title, message)` function using `httpx.post`. Also enables notifications from garmin-sync if run on a server.

**Late wake-up gap** (low)
On an always-on Mac, the 10am launchd job syncs while the user is still asleep — Garmin Connect hasn't finalized sleep data yet. Stats in the notification will be incomplete or from the previous day. Not an issue on a laptop (launchd fires on Mac wake). Fix: add a second sync pass at e.g. noon, or re-run sync on Mac unlock.
