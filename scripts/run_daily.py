#!/usr/bin/env python3
"""
Daily runner — sync Garmin data, generate activity files, notify with today's stats.
Run Tue–Sun at 10am via launchd (com.personalkin.daily.plist).
"""

import subprocess
import sys
from pathlib import Path
from glob import glob

GARMIN_SYNC   = Path.home() / "Projects/garmin-sync"
PERSONALKIN   = Path(__file__).parent.parent
GARMIN_DB     = str(GARMIN_SYNC / "garmin.duckdb")
SYNC_VENV         = str(GARMIN_SYNC / ".venv/bin/python")
MAIN_VENV         = str(PERSONALKIN / ".venv/bin/python")
TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
ENV               = {**__import__("os").environ, "GARMIN_DB": GARMIN_DB}


REPORTS_DIR = PERSONALKIN / "context" / "health" / "reports"


def notify(title, message, open_path=None, sound="default"):
    cmd = [TERMINAL_NOTIFIER, "-title", title, "-message", message, "-sound", sound, "-timeout", "15"]
    if open_path:
        cmd += ["-open", f"file://{open_path}"]
    subprocess.run(cmd)


def run(cmd, cwd=None, label=""):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=ENV)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1]
        notify("❌ Personalkin — Sync Failed", f"{label}: {err[:80]}", sound="Basso")
        sys.exit(1)
    return result.stdout


def get_today_stats():
    import duckdb
    con = duckdb.connect(GARMIN_DB, read_only=True)
    row = con.execute("""
        SELECT sleep_score, sleep_qualifier, hrv_last_night, hrv_weekly_avg,
               training_readiness_score, training_readiness_level, bb_end
        FROM health_days
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    if not row:
        return "synced"
    sleep, qualifier, hrv, hrv_avg, readiness, level, bb = row
    parts = []
    if sleep:
        parts.append(f"😴 Sleep {sleep:.0f} ({(qualifier or '')[:4]})")
    if hrv:
        delta = f" ({'+' if hrv - hrv_avg >= 0 else ''}{hrv - hrv_avg:.0f})" if hrv_avg else ""
        parts.append(f"💓 HRV {hrv:.0f}ms{delta}")
    if bb:
        parts.append(f"🔋 Battery {bb:.0f}")
    if readiness:
        parts.append(f"⚡ Readiness {readiness:.0f} ({(level or '').title()})")
    return "\n".join(parts) if parts else "synced"


if __name__ == "__main__":
    run([SYNC_VENV, "sync.py"], cwd=GARMIN_SYNC, label="garmin sync")
    run([MAIN_VENV, "scripts/generate_activities.py"], cwd=PERSONALKIN, label="activities")
    stats = get_today_stats()
    reports = sorted(glob(str(REPORTS_DIR / "????-W??.md")))
    latest_report = Path(reports[-1]) if reports else None
    notify("⌚ Personalkin — Daily Sync", stats, open_path=latest_report)
