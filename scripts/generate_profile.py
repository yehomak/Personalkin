#!/usr/bin/env python3
"""
Generates context/health-profile.md — comprehensive health reference with baselines.

Usage:
    python scripts/generate_profile.py
    GARMIN_DB=/path/to/garmin.duckdb python scripts/generate_profile.py
"""

import os
from datetime import date
from pathlib import Path

import duckdb

DB_PATH = os.environ.get("GARMIN_DB", str(Path.home() / "Projects/garmin-sync/garmin.duckdb"))
OUTPUT = Path(__file__).parent.parent / "context" / "health" / "profile.md"


def _conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _stat(values):
    """(min, max, avg, count) for non-None values."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None, None, 0
    return min(vals), max(vals), round(sum(vals) / len(vals), 1), len(vals)


def _fmt(v, decimals=1, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}{suffix}"
    return f"{v}{suffix}"


def generate():
    con = _conn()
    today = date.today().isoformat()

    rng = con.execute("""
        SELECT MIN(date), MAX(date), COUNT(*)
        FROM health_days
        WHERE sleep_score IS NOT NULL OR rhr IS NOT NULL OR bb_end IS NOT NULL
    """).fetchone()

    data_from = str(rng[0]) if rng[0] else "—"
    data_to   = str(rng[1]) if rng[1] else "—"
    data_days = rng[2]

    rows = con.execute("""
        SELECT
            date, sleep_score, sleep_qualifier,
            sleep_total_min, sleep_deep_min, sleep_light_min,
            sleep_rem_min, sleep_awake_min,
            sleep_spo2_avg, sleep_rr_avg,
            hrv_last_night, hrv_weekly_avg,
            hrv_baseline_low, hrv_baseline_high, hrv_status,
            rhr, hr_min, hr_max,
            bb_max, bb_min, bb_end,
            stress_avg,
            spo2_avg, spo2_min, rr_waking_avg,
            steps, step_goal, floors_up, distance_km,
            calories_total, calories_active,
            moderate_activity_min, vigorous_activity_min,
            training_readiness_score, training_readiness_level, recovery_time_hours,
            endurance_score, fitness_age
        FROM health_days
        WHERE sleep_score IS NOT NULL OR rhr IS NOT NULL OR bb_end IS NOT NULL
        ORDER BY date
    """).fetchall()

    cols = [
        "date", "sleep_score", "sleep_qualifier",
        "sleep_total_min", "sleep_deep_min", "sleep_light_min",
        "sleep_rem_min", "sleep_awake_min",
        "sleep_spo2_avg", "sleep_rr_avg",
        "hrv_last_night", "hrv_weekly_avg",
        "hrv_baseline_low", "hrv_baseline_high", "hrv_status",
        "rhr", "hr_min", "hr_max",
        "bb_max", "bb_min", "bb_end",
        "stress_avg",
        "spo2_avg", "spo2_min", "rr_waking_avg",
        "steps", "step_goal", "floors_up", "distance_km",
        "calories_total", "calories_active",
        "moderate_activity_min", "vigorous_activity_min",
        "training_readiness_score", "training_readiness_level", "recovery_time_hours",
        "endurance_score", "fitness_age",
    ]
    data = [{k: v for k, v in zip(cols, r)} for r in rows]
    latest = data[-1] if data else {}

    def vals(key):
        return [d[key] for d in data if d.get(key) is not None]

    activities = con.execute("""
        SELECT activity_type, COUNT(*),
               AVG(duration_min), AVG(avg_hr), AVG(training_load)
        FROM health_activities
        GROUP BY activity_type
        ORDER BY COUNT(*) DESC
    """).fetchall()

    lines = []
    a = lines.append

    a("# Health Profile")
    a("")
    a(f"_Generated: {today} · Data: {data_days} day(s) with readings ({data_from} → {data_to})_")
    a("")
    a("---")
    a("")

    # ── Quick Reference ────────────────────────────────────────────────────────
    a("## Quick Reference")
    a("")
    a("| Metric | Latest | Your Range | Your Avg | Normal Range |")
    a("|--------|--------|------------|----------|--------------|")

    def qr(label, key, decimals=0, suffix="", normal=""):
        mn, mx, avg, n = _stat(vals(key))
        latest_v = _fmt(latest.get(key), decimals, suffix)
        rng_v = f"{_fmt(mn, decimals, suffix)}–{_fmt(mx, decimals, suffix)}" if n > 1 else "—"
        avg_v = _fmt(avg, decimals, suffix)
        a(f"| {label} | {latest_v} | {rng_v} | {avg_v} | {normal} |")

    qr("Sleep Score",       "sleep_score",              normal="70–90")
    qr("Sleep Duration",    "sleep_total_min", suffix=" min", normal="420–540 min")
    qr("Deep Sleep",        "sleep_deep_min",  suffix=" min", normal="60–90 min")
    qr("REM Sleep",         "sleep_rem_min",   suffix=" min", normal="90–120 min")
    qr("HRV Last Night",    "hrv_last_night",  suffix=" ms",  normal="personal — track trend")
    qr("HRV Weekly Avg",    "hrv_weekly_avg",  decimals=1, suffix=" ms", normal="personal — track trend")
    qr("Resting HR",        "rhr",             suffix=" bpm", normal="40–70 bpm")
    qr("Body Battery End",  "bb_end",          normal="30–70 typical")
    qr("Stress Avg",        "stress_avg",      normal="< 25 = low")
    qr("Steps",             "steps",           normal="8,000–10,000/day")
    qr("Training Readiness","training_readiness_score", normal="0–100")
    qr("Endurance Score",   "endurance_score", normal="4000+ = excellent")
    qr("Fitness Age",       "fitness_age",     decimals=1, normal="< chronological age")
    a("")

    # ── Sleep ──────────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Sleep")
    a("")
    a(
        "Sleep is the primary recovery mechanism. Garmin measures it via wrist actigraphy "
        "and heart rate — not clinical-grade, but reliable for personal trends."
    )
    a("")
    a("### Sleep Score (0–100)")
    a("")
    a("A composite score: duration + sleep stages + restfulness + SpO2. Above 80 is good; 90+ is excellent.")
    a("")
    mn, mx, avg, n = _stat(vals("sleep_score"))
    a(f"**Your values:** latest {_fmt(latest.get('sleep_score'), 0)} ({latest.get('sleep_qualifier') or '—'}) · avg {_fmt(avg, 1)} · range {_fmt(mn, 0)}–{_fmt(mx, 0)}")
    a("**Normal range:** 70–90 for healthy adults. Below 60 = poor recovery.")
    a("")
    a("### Sleep Duration")
    a("")
    a("Total time asleep — deep + light + REM, not counting awake minutes.")
    a("")
    mn, mx, avg, n = _stat(vals("sleep_total_min"))
    a(f"**Your values:** latest {_fmt(latest.get('sleep_total_min'), 0)} min · avg {_fmt(avg, 0)} min")
    a("**Normal range:** 420–540 min (7–9 h). Under 360 min consistently = sleep debt accumulating.")
    a("")
    a("### Sleep Stages")
    a("")
    a("| Stage | Role | Your Latest | Your Avg | Target |")
    a("|-------|------|-------------|----------|--------|")
    for label, key, role, target in [
        ("Deep (N3)",   "sleep_deep_min",  "Physical repair, immune function, growth hormone release", "60–90 min"),
        ("REM",         "sleep_rem_min",   "Memory consolidation, emotional processing, creativity",   "90–120 min"),
        ("Light (N1/2)","sleep_light_min", "Transition state; brain maintenance",                      "~50% of total"),
        ("Awake",       "sleep_awake_min", "Brief awakenings are normal; > 30 min total = disruption", "< 20 min"),
    ]:
        mn, mx, avg, n = _stat(vals(key))
        a(f"| {label} | {role} | {_fmt(latest.get(key), 0)} min | {_fmt(avg, 0)} min | {target} |")
    a("")
    a("### Sleep SpO2 & Respiration")
    a("")
    a(f"**SpO2 during sleep:** {_fmt(latest.get('sleep_spo2_avg'), 1)}%  ")
    a("Normal: 95–100%. Dips below 90% may indicate sleep apnea — worth investigating if consistent.")
    a("")
    a(f"**Respiration rate during sleep:** {_fmt(latest.get('sleep_rr_avg'), 1)} breaths/min  ")
    a("Normal: 12–20. A rising rate (+2 breaths/min above your norm) is an early illness signal.")
    a("")

    # ── HRV ───────────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## HRV & Autonomic Fitness")
    a("")
    a(
        "Heart Rate Variability measures the millisecond variation between heartbeats. "
        "A higher, more variable HRV signals a well-recovered autonomic nervous system. "
        "It's the most important single recovery signal Garmin tracks."
    )
    a("")
    a("### HRV Last Night")
    a("")
    a("Garmin's primary HRV reading — average HRV during your deepest sleep window (roughly the first 4–6 hours).")
    a("")
    mn, mx, avg, n = _stat(vals("hrv_last_night"))
    a(f"**Your values:** latest {_fmt(latest.get('hrv_last_night'), 0)} ms · avg {_fmt(avg, 0)} ms · range {_fmt(mn, 0)}–{_fmt(mx, 0)} ms")
    a("**Key rule:** HRV is highly individual. A healthy 20-year-old can have 40 ms; an athlete can have 120 ms. Track YOUR baseline — day-to-day drops > 10 ms from your weekly avg are meaningful.")
    a(f"**Garmin status:** {latest.get('hrv_status') or '—'} (needs 2–3 weeks of data to classify properly)")
    a("")
    a("**What suppresses HRV:** alcohol, poor sleep, illness, high training load, travel, stress.")
    a("**What builds HRV:** consistent aerobic training, quality sleep, stress management, rest.")
    a("")
    a("### HRV Weekly Average")
    a("")
    a("Rolling 7-day average of last-night HRV. More stable than the daily reading — use this as your reference baseline.")
    a("")
    mn, mx, avg, n = _stat(vals("hrv_weekly_avg"))
    a(f"**Your values:** latest {_fmt(latest.get('hrv_weekly_avg'), 1)} ms · avg {_fmt(avg, 1)} ms")
    a("")

    bl_low  = latest.get("hrv_baseline_low")
    bl_high = latest.get("hrv_baseline_high")
    if bl_low or bl_high:
        a("### Garmin HRV Baseline Band")
        a("")
        a(f"Your personal balanced range: **{_fmt(bl_low, 0)}–{_fmt(bl_high, 0)} ms**")
        a("")
        a("| Position | Interpretation |")
        a("|----------|---------------|")
        a("| Above band | Unusually recovered — ideal for hard sessions |")
        a("| Within band | Normal — train as planned |")
        a("| Below band | Elevated fatigue — consider easy session or rest |")
        a("")

    # ── Heart Rate ─────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Heart Rate")
    a("")
    a("### Resting Heart Rate (RHR)")
    a("")
    a(
        "Lowest HR recorded during sleep — the most stable long-term cardiovascular fitness indicator. "
        "Improves (lowers) as aerobic fitness builds over months."
    )
    a("")
    mn, mx, avg, n = _stat(vals("rhr"))
    a(f"**Your values:** latest {_fmt(latest.get('rhr'), 0)} bpm · avg {_fmt(avg, 0)} bpm · range {_fmt(mn, 0)}–{_fmt(mx, 0)} bpm")
    a("**Normal range:** 40–70 bpm. Athletes typically 40–55. Below 40 without athletic background warrants a check.")
    a("**Warning signal:** RHR rising 3–5 bpm above your norm = overtraining, illness, or accumulated sleep debt.")
    a("")
    a("### Daily HR Range")
    a("")
    a(f"**HR min (overnight low):** {_fmt(latest.get('hr_min'), 0)} bpm  ")
    a(f"**HR max (daily peak):** {_fmt(latest.get('hr_max'), 0)} bpm  ")
    a("Wide range is normal. A high max with no logged activity suggests stress or stimulants.")
    a("")

    # ── Body Battery ───────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Body Battery & Energy")
    a("")
    a(
        "Garmin's proprietary energy reserve score (0–100), driven by HRV data. "
        "Rises during sleep and rest, drains with physical and mental stress. "
        "Best thought of as 'how much fuel you have left in the tank'."
    )
    a("")
    a("| Reading | What it tells you | Your Latest | Your Avg |")
    a("|---------|------------------|-------------|----------|")
    for label, key, desc in [
        ("BB Max (overnight peak)", "bb_max",
         "How fully you recharged. 80–100 = fully restored; < 60 = sleep didn't recover you"),
        ("BB Min (daily low)",      "bb_min",
         "How depleted you got. < 20 = fully drained; plan a rest day"),
        ("BB End (bedtime level)",  "bb_end",
         "What you go to sleep with. > 30 allows for decent overnight recharge"),
    ]:
        mn, mx, avg, n = _stat(vals(key))
        a(f"| {label} | {desc} | {_fmt(latest.get(key), 0)} | {_fmt(avg, 0)} |")
    a("")
    a("**Watch face priority:** Body Battery is the best real-time energy glance. If it's below 20 midday, skip the hard session.")
    a("")

    # ── Stress ─────────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Stress")
    a("")
    a(
        "Garmin estimates stress from HRV pattern changes throughout the day. "
        "**It does not distinguish between good stress (exercise) and bad stress (anxiety)** — "
        "it measures autonomic load. Scores run 0–100."
    )
    a("")
    a("| Range | Label |")
    a("|-------|-------|")
    a("| 0–25  | Rest / recovery |")
    a("| 26–50 | Low stress |")
    a("| 51–75 | Medium stress |")
    a("| 76–100 | High stress |")
    a("")
    mn, mx, avg, n = _stat(vals("stress_avg"))
    a(f"**Your values:** latest {_fmt(latest.get('stress_avg'), 0)} · avg {_fmt(avg, 0)} · range {_fmt(mn, 0)}–{_fmt(mx, 0)}")
    a("")
    a("**Key relationship:** Stress and Body Battery are inversely linked — sustained high stress (> 50 avg) drains BB fast and suppresses HRV. Consistently high avg stress with low HRV = overreaching.")
    a("")

    # ── SpO2 & Respiration ─────────────────────────────────────────────────────
    a("---")
    a("")
    a("## SpO2 & Respiration")
    a("")
    a(f"**Daytime SpO2 avg:** {_fmt(latest.get('spo2_avg'), 1)}%  ")
    a(f"**Daytime SpO2 min:** {_fmt(latest.get('spo2_min'), 1)}%  ")
    a(f"**Waking respiration rate:** {_fmt(latest.get('rr_waking_avg'), 1)} breaths/min  ")
    a("")
    a("**Normal:** SpO2 95–100%, respiration 12–20 breaths/min.")
    a("")
    a(
        "**Best use case — early illness detection:** SpO2 commonly drops 2–3% and respiration rises 2+ breaths/min "
        "12–24 hours before you feel sick. Catching this early lets you rest before a training cycle breaks down."
    )
    a("")

    # ── Activity ───────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Daily Activity")
    a("")
    a("| Metric | What it measures | Latest | Your Avg | Benchmark |")
    a("|--------|-----------------|--------|----------|-----------|")

    def act_row(label, key, bench, decimals=0, suffix=""):
        mn, mx, avg, n = _stat(vals(key))
        a(f"| {label} | — | {_fmt(latest.get(key), decimals, suffix)} | {_fmt(avg, decimals, suffix)} | {bench} |")

    act_row("Steps",              "steps",                "8,000–10,000/day (WHO)")
    act_row("Distance",           "distance_km",          "varies", decimals=1, suffix=" km")
    act_row("Floors climbed",     "floors_up",            "> 10/day", decimals=1)
    act_row("Active calories",    "calories_active",      "300–600 for active day")
    act_row("Total calories",     "calories_total",       "depends on BMR + activity")
    act_row("Moderate activity",  "moderate_activity_min","150 min/week (WHO)", suffix=" min")
    act_row("Vigorous activity",  "vigorous_activity_min","75 min/week (WHO)", suffix=" min")
    a("")

    # ── Training Readiness ─────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Training Readiness")
    a("")
    a(
        "A 0–100 score that answers: **how hard should I train today?** "
        "Inputs: sleep quality, HRV status, recovery time remaining, and accumulated training load. "
        "Needs 2+ weeks of workouts to be fully accurate."
    )
    a("")
    a("| Score | Level | Recommendation |")
    a("|-------|-------|---------------|")
    a("| 95–100 | Prime | Best sessions, attempts at PRs |")
    a("| 75–94  | High | Train hard as planned |")
    a("| 50–74  | Moderate | Moderate effort — skip intervals |")
    a("| 25–49  | Low | Easy movement only |")
    a("| 0–24   | Poor | Full rest |")
    a("")
    mn, mx, avg, n = _stat(vals("training_readiness_score"))
    a(f"**Your values:** latest {_fmt(latest.get('training_readiness_score'), 0)} ({latest.get('training_readiness_level') or '—'}) · avg {_fmt(avg, 0)} · range {_fmt(mn, 0)}–{_fmt(mx, 0)}")
    rec = latest.get("recovery_time_hours")
    if rec is not None:
        a(f"**Recovery time remaining:** {rec} h")
    a("")

    # ── Fitness Markers ────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Fitness Markers")
    a("")
    a("### Endurance Score (0–6000+)")
    a("")
    a(
        "Garmin's aerobic endurance estimate derived from training history and HR data. "
        "Combines VO2max estimate with training consistency — builds slowly over months of cardio."
    )
    a("")
    a("| Range | Level |")
    a("|-------|-------|")
    a("| 0–1000   | Beginner |")
    a("| 1000–2500 | Fair |")
    a("| 2500–4000 | Good |")
    a("| 4000–5000 | Excellent |")
    a("| 5000+     | Elite |")
    a("")
    mn, mx, avg, n = _stat(vals("endurance_score"))
    a(f"**Your score:** {_fmt(latest.get('endurance_score'), 0)} · avg {_fmt(avg, 0)}")
    a("Builds with consistent cardio over months. Drops during detraining.")
    a("")
    a("### Fitness Age")
    a("")
    a(
        "Garmin's physiological age estimate — based on RHR, HRV, activity levels, and endurance score. "
        "Lower than your calendar age = good cardiovascular fitness. "
        "Improves with: aerobic training, better sleep, lower resting HR."
    )
    a("")
    mn, mx, avg, n = _stat(vals("fitness_age"))
    a(f"**Your fitness age:** {_fmt(latest.get('fitness_age'), 1)} · avg {_fmt(avg, 1)}")
    a("")

    # ── Activity History ───────────────────────────────────────────────────────
    if activities:
        a("---")
        a("")
        a("## Activity History")
        a("")
        a("| Activity Type | Sessions | Avg Duration | Avg HR | Avg Load |")
        a("|--------------|----------|-------------|--------|----------|")
        for act_type, count, avg_dur, avg_hr, avg_load in activities:
            a(f"| {act_type or 'unknown'} | {count} | {_fmt(avg_dur, 0)} min | {_fmt(avg_hr, 0)} bpm | {_fmt(avg_load, 0)} |")
        a("")

    # ── Metric Relationships ───────────────────────────────────────────────────
    a("---")
    a("")
    a("## How Metrics Connect")
    a("")
    a("```")
    a("Sleep quality ──► HRV ──► Training Readiness ──► how hard to push today")
    a("Stress load  ──►──────┘")
    a("")
    a("Body Battery = HRV-driven energy model:")
    a("  charges overnight (rate depends on HRV quality)")
    a("  drains with stress + physical activity")
    a("")
    a("HRV + RHR together:")
    a("  HRV low + RHR elevated  → likely sick or overtrained")
    a("  HRV low + RHR normal    → stress-driven, not illness")
    a("  HRV low + RHR low       → fatigue without cardiac stress (travel, alcohol)")
    a("  Both improving over weeks → genuine fitness adaptation")
    a("")
    a("SpO2 + respiration rate = early warning system:")
    a("  SpO2 drops 2–3% before you feel sick")
    a("  RR rises 2+ breaths/min before symptoms appear")
    a("  Catching either signal = rest day before the illness breaks training")
    a("```")
    a("")

    # ── Watch Face Guide ───────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Watch Face Widget Guide")
    a("")
    a("| Question | Best widget | Runner-up |")
    a("|----------|-------------|-----------|")
    a("| Am I recovered? | Training Readiness | HRV Status |")
    a("| How hard can I train today? | Training Readiness | Body Battery |")
    a("| How's my energy right now? | Body Battery | Stress |")
    a("| Am I about to get sick? | SpO2 | Respiration Rate |")
    a("| Long-term fitness trajectory | Fitness Age | Endurance Score |")
    a("| Sleep quality at a glance | Sleep Score | — |")
    a("| Mental/work stress today | Stress | Body Battery drain rate |")
    a("")
    a("**Recommended daily face (actionable trio):** Training Readiness + Body Battery + Steps")
    a("")

    # ── Primary vs Secondary ───────────────────────────────────────────────────
    a("---")
    a("")
    a("## Metric Priority (for future insights)")
    a("")
    a("**Primary signals** — check daily, drive decisions:")
    a("")
    a("| Metric | Why primary |")
    a("|--------|-------------|")
    a("| HRV Last Night | Best single recovery signal |")
    a("| Training Readiness | Synthesizes everything into one action score |")
    a("| Body Battery | Real-time energy state |")
    a("| Sleep Score | Foundation everything else sits on |")
    a("| Resting HR | Best long-term cardiovascular trend |")
    a("")
    a("**Secondary signals** — useful for context and investigation:")
    a("")
    a("| Metric | When it matters |")
    a("|--------|----------------|")
    a("| Sleep stages (deep/REM) | When sleep score is unexpectedly low |")
    a("| SpO2 / RR | Illness detection |")
    a("| Stress avg | Correlate with busy work weeks or travel |")
    a("| Steps | Baseline activity level |")
    a("| Endurance score | Long-term aerobic fitness trend (months) |")
    a("| Fitness age | Long-term health trajectory |")
    a("")

    # ── Footer ─────────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("_Profile generated by `scripts/generate_profile.py` · Re-run after accumulating more data_")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines))
    print(f"Written: {OUTPUT} ({data_days} day(s) of data)")


if __name__ == "__main__":
    generate()
