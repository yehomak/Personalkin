#!/usr/bin/env python3
"""
Weekly runner — sync, generate weekly report, notify with stats.
Run every Monday at 8am.

Cron: 0 8 * * 1  /Users/yegormakarenko/Projects/Personalkin/.venv/bin/python
      /Users/yegormakarenko/Projects/Personalkin/scripts/run_weekly.py
"""

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

GARMIN_SYNC = Path.home() / "Projects/garmin-sync"
PERSONALKIN = Path(__file__).parent.parent
GARMIN_DB         = str(GARMIN_SYNC / "garmin.duckdb")
SYNC_VENV         = str(GARMIN_SYNC / ".venv/bin/python")
MAIN_VENV         = str(PERSONALKIN / ".venv/bin/python")
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
REPORTS_DIR       = PERSONALKIN / "context" / "health" / "reports"
ENV               = {**os.environ, "GARMIN_DB": GARMIN_DB}


def notify(title, message, open_path=None, sound="default"):
    cmd = [TERMINAL_NOTIFIER, "-title", title, "-message", message, "-sound", sound]
    if open_path:
        cmd += ["-open", f"file://{open_path}"]
    subprocess.run(cmd)


def notify_failure(step, error):
    notify("Personalkin — Weekly Sync Failed", f"{step}: {error[:80]}", sound="Basso")


def run(cmd, cwd=None, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=ENV)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1]
        notify_failure(label, err)
        sys.exit(1)
    return result.stdout


def get_stats(start, end):
    con = duckdb.connect(GARMIN_DB, read_only=True)

    row = con.execute("""
        SELECT
            ROUND(AVG(sleep_score))                  AS avg_sleep,
            ROUND(AVG(hrv_last_night))               AS avg_hrv,
            ROUND(AVG(training_readiness_score))     AS avg_readiness
        FROM health_days
        WHERE date BETWEEN ? AND ?
          AND (sleep_score IS NOT NULL OR hrv_last_night IS NOT NULL)
    """, [start, end]).fetchone()

    workouts = con.execute(
        "SELECT COUNT(*) FROM health_activities WHERE date BETWEEN ? AND ?",
        [start, end]
    ).fetchone()[0]

    avg_sleep, avg_hrv, avg_readiness = row
    parts = []
    if avg_sleep:
        parts.append(f"Sleep {avg_sleep:.0f}")
    if avg_hrv:
        parts.append(f"HRV {avg_hrv:.0f}ms")
    if workouts:
        parts.append(f"{workouts} workout{'s' if workouts > 1 else ''}")
    if avg_readiness:
        parts.append(f"Readiness {avg_readiness:.0f}")

    return " · ".join(parts) if parts else "synced"


if __name__ == "__main__":
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    week_label = monday.strftime("%G-W%V")

    run([SYNC_VENV, "sync.py"], cwd=GARMIN_SYNC, label="garmin sync")
    run([MAIN_VENV, "scripts/generate_activities.py"], cwd=PERSONALKIN, label="activities")
    run([MAIN_VENV, "scripts/generate_report.py"], cwd=PERSONALKIN, label="weekly report")

    stats       = get_stats(monday.isoformat(), sunday.isoformat())
    report_path = REPORTS_DIR / f"{week_label}.md"

    notify(
        title=f"Personalkin — Week {week_label}",
        message=stats,
        open_path=report_path if report_path.exists() else None,
    )
    print(f"Done — {week_label}: {stats}")
