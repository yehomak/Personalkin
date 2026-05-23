#!/usr/bin/env python3
"""
Daily runner — sync Garmin data and generate activity files.
Silent on success. macOS notification on failure.

Cron: 0 8 * * 2-7  /Users/yegormakarenko/Projects/Personalkin/.venv/bin/python
      /Users/yegormakarenko/Projects/Personalkin/scripts/run_daily.py
"""

import subprocess
import sys
from pathlib import Path

GARMIN_SYNC   = Path.home() / "Projects/garmin-sync"
PERSONALKIN   = Path(__file__).parent.parent
GARMIN_DB     = str(GARMIN_SYNC / "garmin.duckdb")
SYNC_VENV         = str(GARMIN_SYNC / ".venv/bin/python")
MAIN_VENV         = str(PERSONALKIN / ".venv/bin/python")
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
ENV               = {**__import__("os").environ, "GARMIN_DB": GARMIN_DB}


def notify(title, message, sound="default"):
    subprocess.run([TERMINAL_NOTIFIER, "-title", title, "-message", message, "-sound", sound])


def run(cmd, cwd=None, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=ENV)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1]
        notify("Personalkin — Sync Failed", f"{label}: {err[:80]}", sound="Basso")
        sys.exit(1)
    return result.stdout


def get_today_stats():
    import duckdb
    con = duckdb.connect(GARMIN_DB, read_only=True)
    row = con.execute("""
        SELECT sleep_score, sleep_qualifier, hrv_last_night,
               training_readiness_score, training_readiness_level, bb_end
        FROM health_days
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    if not row:
        return "synced"
    sleep, qualifier, hrv, readiness, level, bb = row
    parts = []
    if sleep:
        parts.append(f"Sleep {sleep:.0f} ({(qualifier or '')[:4]})")
    if hrv:
        parts.append(f"HRV {hrv:.0f}ms")
    if readiness:
        parts.append(f"Readiness {readiness:.0f} ({(level or '').title()})")
    return " · ".join(parts) if parts else "synced"


if __name__ == "__main__":
    run([SYNC_VENV, "sync.py"], cwd=GARMIN_SYNC, label="garmin sync")
    run([MAIN_VENV, "scripts/generate_activities.py"], cwd=PERSONALKIN, label="activities")
    stats = get_today_stats()
    notify("Personalkin — Daily Sync", stats)
