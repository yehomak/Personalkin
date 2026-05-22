import json
import os
from datetime import date, timedelta
from pathlib import Path

import duckdb

DB_PATH = os.environ.get(
    "GARMIN_DB",
    str(Path.home() / "Projects/garmin-sync/garmin.duckdb"),
)


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
    Returns daily readiness score/level and all workouts with type, duration, HR, and training load.
    Use this to assess training volume, recovery balance, and overreaching risk.
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
            hr_zone4_min, hr_zone5_min
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
                "hr_zone4_min": r[10], "hr_zone5_min": r[11],
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
