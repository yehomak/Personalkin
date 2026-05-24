#!/usr/bin/env python3
"""
Monthly runner — generate monthly report for the previous month, notify with stats.
Run on the 1st of each month at 10am via launchd (com.personalkin.monthly.plist).
"""

import os
import subprocess
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import duckdb

GARMIN_SYNC = Path.home() / "Projects/garmin-sync"
PERSONALKIN = Path(__file__).parent.parent
GARMIN_DB         = str(GARMIN_SYNC / "garmin.duckdb")
MAIN_VENV         = str(PERSONALKIN / ".venv/bin/python")
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
REPORTS_DIR       = PERSONALKIN / "context" / "health" / "reports"
ENV               = {**os.environ, "GARMIN_DB": GARMIN_DB}


def notify(title, message, open_path=None, sound="default"):
    cmd = [TERMINAL_NOTIFIER, "-title", title, "-message", message, "-sound", sound, "-timeout", "15"]
    if open_path:
        cmd += ["-open", f"file://{open_path}"]
    subprocess.run(cmd)


def notify_failure(step, error):
    notify("❌ Personalkin — Monthly Report Failed", f"{step}: {error[:80]}", sound="Basso")


def run(cmd, cwd=None, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=ENV)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1]
        notify_failure(label, err)
        sys.exit(1)
    return result.stdout


def get_stats(year, month):
    last_day = monthrange(year, month)[1]
    start    = date(year, month, 1).isoformat()
    end      = date(year, month, last_day).isoformat()

    con = duckdb.connect(GARMIN_DB, read_only=True)

    row = con.execute("""
        SELECT
            ROUND(AVG(sleep_score))       AS avg_sleep,
            ROUND(AVG(hrv_last_night))    AS avg_hrv,
            MIN(endurance_score)          AS endurance_start,
            MAX(endurance_score)          AS endurance_end
        FROM health_days
        WHERE date BETWEEN ? AND ?
          AND (sleep_score IS NOT NULL OR hrv_last_night IS NOT NULL)
    """, [start, end]).fetchone()

    workouts = con.execute(
        "SELECT COUNT(*) FROM health_activities WHERE date BETWEEN ? AND ?",
        [start, end]
    ).fetchone()[0]

    avg_sleep, avg_hrv, e_start, e_end = row
    parts = []
    if workouts:
        parts.append(f"🏋️ {workouts} workout{'s' if workouts > 1 else ''}")
    if avg_sleep:
        parts.append(f"😴 Sleep avg {avg_sleep:.0f}")
    if avg_hrv:
        parts.append(f"💓 HRV avg {avg_hrv:.0f}ms")
    if e_start and e_end and e_start != e_end:
        delta = e_end - e_start
        parts.append(f"📈 Endurance {'+' if delta >= 0 else ''}{delta:.0f}")

    return "\n".join(parts) if parts else "ready"


if __name__ == "__main__":
    today = date.today()
    # Generate report for the previous month
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1

    month_label = f"{year}-{month:02d}"
    month_name  = date(year, month, 1).strftime("%B %Y")

    run(
        [MAIN_VENV, "scripts/generate_monthly_report.py", "--month", month_label],
        cwd=PERSONALKIN,
        label="monthly report",
    )

    stats       = get_stats(year, month)
    report_path = REPORTS_DIR / f"{month_label}.md"

    notify(
        title=f"📆 Personalkin — {month_name}",
        message=stats,
        open_path=report_path if report_path.exists() else None,
    )
    print(f"Done — {month_label}: {stats}")
