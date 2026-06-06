import json
import os
from datetime import date, timedelta
from pathlib import Path

import duckdb

HEALTH_DIR = Path(__file__).parent.parent / "context" / "health"

DB_PATH = os.environ.get("GARMIN_DB")
if not DB_PATH:
    raise RuntimeError("GARMIN_DB env var is not set — add it to ~/.claude.json MCP server env block")


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def _days_back(days: int) -> str:
    return (date.today() - timedelta(days=days - 1)).isoformat()


def get_health_snapshot() -> str:
    """
    Today's health metrics at a glance — the most recent synced day.
    Covers sleep, HRV, resting HR, Body Battery, stress, steps, and training readiness.
    Use this for a quick current-state summary before asking deeper questions.
    """
    conn = _conn()
    row = conn.execute(
        """
        SELECT
            date, sleep_score, sleep_qualifier, sleep_total_min,
            sleep_deep_min, sleep_rem_min,
            hrv_last_night, hrv_weekly_avg, hrv_status,
            rhr, bb_max, bb_min, bb_end,
            stress_avg, steps, calories_active,
            training_readiness_score, training_readiness_level,
            recovery_time_hours, endurance_score, fitness_age
        FROM health_days
        ORDER BY date DESC
        LIMIT 1
        """
    ).fetchone()

    if not row:
        return json.dumps({"error": "No health data found. Run sync.py first."})

    keys = [
        "date", "sleep_score", "sleep_qualifier", "sleep_total_min",
        "sleep_deep_min", "sleep_rem_min",
        "hrv_last_night", "hrv_weekly_avg", "hrv_status",
        "rhr", "bb_max", "bb_min", "bb_end",
        "stress_avg", "steps", "calories_active",
        "training_readiness_score", "training_readiness_level",
        "recovery_time_hours", "endurance_score", "fitness_age",
    ]
    return json.dumps(
        {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in zip(keys, row)},
        indent=2,
    )


def get_sleep_trend(days: int = 14) -> str:
    """
    Sleep quality and duration trend for the past N days.
    Returns per-day breakdown: score, total/deep/REM minutes, SpO2, respiration.
    Useful for spotting degraded sleep around travel, stress, or training spikes.
    """
    start = _days_back(days)
    conn = _conn()
    rows = conn.execute(
        """
        SELECT
            date, sleep_score, sleep_qualifier,
            sleep_total_min, sleep_deep_min, sleep_light_min,
            sleep_rem_min, sleep_awake_min,
            sleep_spo2_avg, sleep_rr_avg
        FROM health_days
        WHERE date >= ? AND sleep_score IS NOT NULL
        ORDER BY date
        """,
        [start],
    ).fetchall()

    data = [
        {
            "date": str(r[0]),
            "score": r[1], "qualifier": r[2],
            "total_min": r[3], "deep_min": r[4], "light_min": r[5],
            "rem_min": r[6], "awake_min": r[7],
            "spo2_avg": r[8], "rr_avg": r[9],
        }
        for r in rows
    ]
    avg_score = round(sum(d["score"] for d in data if d["score"]) / max(1, sum(1 for d in data if d["score"])), 1)
    avg_total = round(sum(d["total_min"] for d in data if d["total_min"]) / max(1, sum(1 for d in data if d["total_min"])), 1)
    return json.dumps({
        "from": start, "days": len(data),
        "avg_score": avg_score, "avg_total_min": avg_total,
        "entries": data,
    }, indent=2)


def get_hrv_trend(days: int = 30) -> str:
    """
    HRV and resting heart rate trend for the past N days.
    Returns last-night HRV, weekly average, baseline bounds, status, and RHR per day.
    HRV is the primary recovery signal — use this to correlate with training load, travel, or stress.
    """
    start = _days_back(days)
    conn = _conn()
    rows = conn.execute(
        """
        SELECT
            date, hrv_last_night, hrv_weekly_avg,
            hrv_baseline_low, hrv_baseline_high, hrv_status, rhr
        FROM health_days
        WHERE date >= ? AND (hrv_last_night IS NOT NULL OR rhr IS NOT NULL)
        ORDER BY date
        """,
        [start],
    ).fetchall()

    data = [
        {
            "date": str(r[0]),
            "hrv_last_night": r[1], "hrv_weekly_avg": r[2],
            "hrv_baseline_low": r[3], "hrv_baseline_high": r[4],
            "hrv_status": r[5], "rhr": r[6],
        }
        for r in rows
    ]
    hrv_vals = [d["hrv_last_night"] for d in data if d["hrv_last_night"]]
    avg_hrv = round(sum(hrv_vals) / len(hrv_vals), 1) if hrv_vals else None
    avg_rhr = round(sum(d["rhr"] for d in data if d["rhr"]) / max(1, sum(1 for d in data if d["rhr"])), 1)
    return json.dumps({
        "from": start, "days": len(data),
        "avg_hrv_last_night": avg_hrv, "avg_rhr": avg_rhr,
        "entries": data,
    }, indent=2)


def get_body_battery_trend(days: int = 14) -> str:
    """
    Body Battery and stress trend for the past N days.
    Returns daily high/low/end BB values and average stress.
    Use this to see energy drain patterns across busy periods, travel, or training blocks.
    """
    start = _days_back(days)
    conn = _conn()
    rows = conn.execute(
        """
        SELECT date, bb_max, bb_min, bb_end, stress_avg
        FROM health_days
        WHERE date >= ? AND bb_end IS NOT NULL
        ORDER BY date
        """,
        [start],
    ).fetchall()

    data = [
        {"date": str(r[0]), "bb_max": r[1], "bb_min": r[2], "bb_end": r[3], "stress_avg": r[4]}
        for r in rows
    ]
    avg_end = round(sum(d["bb_end"] for d in data if d["bb_end"]) / max(1, sum(1 for d in data if d["bb_end"])), 1)
    avg_stress = round(sum(d["stress_avg"] for d in data if d["stress_avg"]) / max(1, sum(1 for d in data if d["stress_avg"])), 1)
    return json.dumps({
        "from": start, "days": len(data),
        "avg_bb_end": avg_end, "avg_stress": avg_stress,
        "entries": data,
    }, indent=2)


def get_training_load(days: int = 14) -> str:
    """
    Training readiness and activity log for the past N days.
    Returns daily readiness score/level and all workouts with type, duration, HR, training load,
    full HR zone breakdown (z1–z5 minutes), and pace (for GPS activities like running).
    Use this to assess training volume, zone distribution, recovery balance, and overreaching risk.
    avg_pace_min_km is null for non-GPS activities (strength, MMA, etc.).
    """
    start = _days_back(days)
    conn = _conn()

    readiness = conn.execute(
        """
        SELECT date, training_readiness_score, training_readiness_level, recovery_time_hours
        FROM health_days
        WHERE date >= ? AND training_readiness_score IS NOT NULL
        ORDER BY date
        """,
        [start],
    ).fetchall()

    activities = conn.execute(
        """
        SELECT
            date, start_time, activity_type, duration_min,
            avg_hr, max_hr, calories, training_load,
            training_effect_aerobic, training_effect_anaerobic,
            hr_zone1_min, hr_zone2_min, hr_zone3_min, hr_zone4_min, hr_zone5_min,
            avg_pace_min_km
        FROM health_activities
        WHERE date >= ?
        ORDER BY date, start_time
        """,
        [start],
    ).fetchall()

    return json.dumps({
        "from": start,
        "readiness": [
            {
                "date": str(r[0]), "score": r[1],
                "level": r[2], "recovery_time_hours": r[3],
            }
            for r in readiness
        ],
        "activities": [
            {
                "date": str(r[0]), "start_time": str(r[1]) if r[1] else None,
                "type": r[2], "duration_min": r[3],
                "avg_hr": r[4], "max_hr": r[5], "calories": r[6],
                "training_load": r[7],
                "aerobic_effect": r[8], "anaerobic_effect": r[9],
                "hr_zones": {
                    "z1": r[10], "z2": r[11], "z3": r[12],
                    "z4": r[13], "z5": r[14],
                },
                "avg_pace_min_km": r[15],
            }
            for r in activities
        ],
    }, indent=2)


def get_health_on_date(date: str) -> str:
    """
    All health metrics for a specific date (YYYY-MM-DD).
    Returns the full daily record — sleep, HRV, HR, BB, stress, readiness, fitness metrics.
    Use this when cross-referencing health with a specific calendar event or spending date.
    """
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM health_days WHERE date = ?", [date]
    ).fetchone()

    if not row:
        return json.dumps({"error": f"No data for {date}. May not have been synced yet."})

    cols = [d[0] for d in conn.execute("DESCRIBE health_days").fetchall()]
    result = {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in zip(cols, row)}

    activities = conn.execute(
        """
        SELECT activity_type, duration_min, avg_hr, training_load
        FROM health_activities WHERE date = ?
        ORDER BY start_time
        """,
        [date],
    ).fetchall()

    result["activities"] = [
        {"type": r[0], "duration_min": r[1], "avg_hr": r[2], "training_load": r[3]}
        for r in activities
    ]
    return json.dumps(result, indent=2)


def get_health_in_range(from_date: str, to_date: str) -> str:
    """
    Health summary for a date range (YYYY-MM-DD to YYYY-MM-DD).
    Returns per-day key metrics and all activities in the period.
    Ideal for analysing health impact of trips, events, or training blocks.
    """
    conn = _conn()
    rows = conn.execute(
        """
        SELECT
            date, sleep_score, sleep_total_min,
            hrv_last_night, rhr, bb_min, bb_end,
            stress_avg, steps, training_readiness_score, training_readiness_level
        FROM health_days
        WHERE date BETWEEN ? AND ?
        ORDER BY date
        """,
        [from_date, to_date],
    ).fetchall()

    days = [
        {
            "date": str(r[0]),
            "sleep_score": r[1], "sleep_total_min": r[2],
            "hrv_last_night": r[3], "rhr": r[4],
            "bb_min": r[5], "bb_end": r[6],
            "stress_avg": r[7], "steps": r[8],
            "readiness_score": r[9], "readiness_level": r[10],
        }
        for r in rows
    ]

    activities = conn.execute(
        """
        SELECT date, activity_type, duration_min, training_load
        FROM health_activities
        WHERE date BETWEEN ? AND ?
        ORDER BY date
        """,
        [from_date, to_date],
    ).fetchall()

    scored = [d for d in days if d["sleep_score"]]
    hrv_vals = [d["hrv_last_night"] for d in days if d["hrv_last_night"]]
    return json.dumps({
        "from": from_date, "to": to_date,
        "days_with_data": len(days),
        "avg_sleep_score": round(sum(d["sleep_score"] for d in scored) / len(scored), 1) if scored else None,
        "avg_hrv": round(sum(hrv_vals) / len(hrv_vals), 1) if hrv_vals else None,
        "activities": len(activities),
        "days": days,
        "activity_log": [
            {"date": str(r[0]), "type": r[1], "duration_min": r[2], "training_load": r[3]}
            for r in activities
        ],
    }, indent=2)


def get_health_profile() -> str:
    """
    Full health reference profile — all Garmin metrics with descriptions, normal ranges,
    and your personal baselines.
    Covers: sleep stages, HRV, RHR, Body Battery, stress, SpO2, training readiness,
    endurance score, fitness age, metric relationships, and watch face widget guide.
    Use this to understand what a metric means or to build cross-domain insights.
    Run scripts/generate_profile.py to regenerate after accumulating more data.
    """
    path = HEALTH_DIR / "profile.md"
    if not path.exists():
        return json.dumps({
            "error": "health-profile.md not found. Run: python scripts/generate_profile.py"
        })
    return path.read_text()


def get_latest_health_report() -> str:
    """
    Most recent weekly health report (YYYY-WXX) — narrative summary, 7-day trends with
    ASCII sparklines, day-by-day table, sleep detail, training section with explanations,
    highlights, baseline comparison, and raw data.
    Run scripts/generate_report.py to regenerate for the current week.
    """
    reports_dir = HEALTH_DIR / "reports" / "weekly"
    if not reports_dir.exists():
        return json.dumps({"error": "No health reports found. Run: python scripts/generate_report.py"})
    reports = sorted(reports_dir.glob("????-??-??.md"), reverse=True)
    if not reports:
        return json.dumps({"error": "No weekly reports found. Run: python scripts/generate_report.py"})
    return reports[0].read_text()


def get_latest_monthly_report() -> str:
    """
    Most recent monthly health report (YYYY-MM) — month averages vs prior baseline,
    fitness trajectory, training volume by type, week-by-week breakdown, highlights,
    and full raw data table.
    Run scripts/generate_monthly_report.py to regenerate.
    """
    reports_dir = HEALTH_DIR / "reports" / "monthly"
    if not reports_dir.exists():
        return json.dumps({"error": "No reports found. Run: python scripts/generate_monthly_report.py"})
    reports = sorted(reports_dir.glob("????-??.md"), reverse=True)
    if not reports:
        return json.dumps({"error": "No monthly reports found. Run: python scripts/generate_monthly_report.py"})
    return reports[0].read_text()


def get_activity_report(activity_date: str) -> str:
    """
    Per-activity breakdown for a specific date (YYYY-MM-DD).
    Covers: key metrics, pace, training effect with explanation, HR zone breakdown,
    effort context, recovery impact on next-day HRV and readiness, and raw data.
    If multiple activities exist for the date, returns all of them concatenated.
    Run scripts/generate_activities.py to generate activity files.
    """
    activities_dir = HEALTH_DIR / "activities"  # context/health/activities/
    if not activities_dir.exists():
        return json.dumps({"error": "No activity reports. Run: python scripts/generate_activities.py"})
    files = sorted(activities_dir.glob(f"{activity_date}-*.md"))
    if not files:
        return json.dumps({"error": f"No activity report for {activity_date}. Run: python scripts/generate_activities.py --date {activity_date}"})
    return "\n\n---\n\n".join(f.read_text() for f in files)
