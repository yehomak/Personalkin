#!/usr/bin/env python3
"""
Daily runner — sync Garmin data, regenerate weekly report, notify with today's stats.
Run Mon–Sun at 10am via launchd (com.personalkin.daily.plist).
"""

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

GARMIN_SYNC   = Path(os.environ.get("GARMIN_SYNC", str(Path.home() / "Projects/garmin-sync")))
PERSONALKIN   = Path(__file__).parent.parent
GARMIN_DB     = str(GARMIN_SYNC / "garmin.duckdb")
SYNC_VENV         = str(GARMIN_SYNC / ".venv/bin/python")
MAIN_VENV         = str(PERSONALKIN / ".venv/bin/python")
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
ENV               = {**__import__("os").environ, "GARMIN_DB": GARMIN_DB}


REPORTS_DIR   = PERSONALKIN / "context" / "health" / "reports" / "weekly"
ICON_PATH     = PERSONALKIN / "assets" / "icon.png"
CHECKIN_PROMPT = PERSONALKIN / "scripts" / "checkin_prompt.sh"


def notify(title, subtitle=None, message=None, open_path=None, sound="default"):
    cmd = [TERMINAL_NOTIFIER, "-title", title, "-sound", sound, "-timeout", "15",
           "-group", "personalkin-daily"]
    if subtitle:
        cmd += ["-subtitle", subtitle]
    if message:
        cmd += ["-message", message]
    if ICON_PATH.exists():
        cmd += ["-contentImage", str(ICON_PATH)]
    if open_path:
        cmd += ["-open", f"file://{open_path}"]
    subprocess.run(cmd)


def notify_checkin():
    cmd = [
        TERMINAL_NOTIFIER,
        "-title", "Check in",
        "-message", "Mood · Energy · Training?",
        "-actions", "Log",
        "-execute", f"bash {CHECKIN_PROMPT}",
        "-timeout", "3600",
        "-group", "personalkin-checkin",
        "-sound", "none",
    ]
    if ICON_PATH.exists():
        cmd += ["-contentImage", str(ICON_PATH)]
    subprocess.Popen(cmd)


def run(cmd, cwd=None, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=ENV)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1]
        notify("❌ Personalkin — Sync Failed", message=f"{label}: {err[:80]}", sound="Basso")
        sys.exit(1)
    return result.stdout


def get_today_stats():
    import duckdb
    con = duckdb.connect(GARMIN_DB, read_only=True)
    # Use the most recent row that has at least one stat — Garmin data for today
    # often isn't processed yet at 10am, so fall back to the previous day's row.
    rows = con.execute("""
        SELECT sleep_score, sleep_qualifier, hrv_last_night, hrv_weekly_avg,
               training_readiness_score, training_readiness_level, bb_end
        FROM health_days
        ORDER BY date DESC LIMIT 3
    """).fetchall()
    # Prefer a row with core overnight stats; fall back to any row with data.
    row = next((r for r in rows if any(v is not None for v in (r[0], r[2], r[4]))), None)
    if row is None:
        row = next((r for r in rows if any(v is not None for v in r)), None)
    if not row:
        return "synced"
    sleep, qualifier, hrv, hrv_avg, readiness, level, bb = row

    # Compact one-line subtitle: all key metrics
    # Title: readiness — the most actionable metric, bold and always visible
    if readiness is not None:
        title = f"⌚ Personalkin  ·  ⚡{readiness:.0f} {(level or '').title()}"
    else:
        title = "⌚ Personalkin — Daily Sync"

    # Subtitle: 3 physiological metrics — safely fits in one line
    stat_parts = []
    if sleep:
        stat_parts.append(f"😴{sleep:.0f}")
    if hrv:
        delta = f"{'+' if hrv - hrv_avg >= 0 else ''}{hrv - hrv_avg:.0f}" if hrv_avg else ""
        stat_parts.append(f"💓{hrv:.0f}ms" + (f"{delta}" if delta else ""))
    if bb is not None:
        stat_parts.append(f"🔋{bb:.0f}")
    subtitle = " · ".join(stat_parts) if stat_parts else None

    # Message: coaching tip
    if readiness is not None:
        if readiness >= 80:
            tip = "Well recovered — good day to train"
        elif readiness >= 60:
            tip = "Moderate readiness — keep intensity light"
        elif readiness >= 40:
            tip = "Low readiness — skip hard training"
        else:
            tip = "Rest day — body needs full recovery"
    elif bb is not None and bb < 20:
        tip = "Low energy — rest or easy activity today"
    else:
        tip = None

    return title, subtitle, tip


if __name__ == "__main__":
    today      = date.today()
    week_label = today.strftime("%G-W%V")
    monday     = today - timedelta(days=today.weekday())

    run([SYNC_VENV, "sync.py"], cwd=GARMIN_SYNC, label="garmin sync")
    run([MAIN_VENV, "scripts/generate_activities.py"], cwd=PERSONALKIN, label="activities")
    run([MAIN_VENV, "scripts/generate_report.py", "--week", week_label], cwd=PERSONALKIN, label="weekly report")

    title, subtitle, tip = get_today_stats()
    report_path   = REPORTS_DIR / monday.strftime("%Y-%m-%d.md")
    notify(title, subtitle=subtitle, message=tip,
           open_path=report_path if report_path.exists() else None)
    notify_checkin()
