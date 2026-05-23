#!/usr/bin/env python3
"""
Generates per-activity markdown files in context/activities/.
Creates one file per activity: YYYY-MM-DD-activity-type.md

Usage:
    python scripts/generate_activities.py              # all unwritten activities
    python scripts/generate_activities.py --date 2026-05-22
    python scripts/generate_activities.py --all        # regenerate all
"""

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

import duckdb

DB_PATH        = os.environ.get("GARMIN_DB", str(Path.home() / "Projects/garmin-sync/garmin.duckdb"))
ACTIVITIES_DIR = Path(__file__).parent.parent / "context" / "health" / "activities"

BARS = "▁▂▃▄▅▆▇█"

TE_LABELS = {
    (0.0, 2.0): ("Recovery",         "Minimal training stimulus. Good for active recovery days."),
    (2.0, 3.0): ("Maintaining",      "Keeps current fitness but won't build it. Fine for easy days."),
    (3.0, 4.0): ("Improving",        "Solid stimulus. This session contributes meaningfully to fitness."),
    (4.0, 5.0): ("Highly Improving", "Hard work — high adaptation potential. Requires adequate recovery."),
    (5.0, 99.): ("Overreaching",     "Exceeded recommended intensity. Risk of accumulated fatigue if repeated."),
}

HR_ZONES = [
    ("Zone 1 — Very Light",  "< 60% max HR",  "Recovery. Fat oxidation. Full conversation possible. Foundation of base building."),
    ("Zone 2 — Light",       "60–70% max HR", "Aerobic base. The most important zone for endurance. Should feel easy, sustainable for hours."),
    ("Zone 3 — Moderate",    "70–80% max HR", "Aerobic tempo. Harder to hold conversation. Builds aerobic capacity and economy."),
    ("Zone 4 — Hard",        "80–90% max HR", "Lactate threshold. Breathing is laboured. Sustainable for 30–60 min max. High training value."),
    ("Zone 5 — Maximum",     "90–100% max HR","VO2max zone. Very short intervals only. Cannot sustain > a few minutes. Builds peak power."),
]

LOAD_CONTEXT = [
    (0,   100, "Low — easy session, minimal fatigue"),
    (100, 200, "Moderate — solid training, manageable recovery"),
    (200, 300, "High — hard session, 24–48 h recovery"),
    (300, 999, "Very high — significant fatigue, prioritise sleep and nutrition"),
]


def _conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _fmt(v, decimals=1, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}{suffix}"
    return f"{v}{suffix}"


def _te_info(te):
    if te is None:
        return "—", ""
    for (lo, hi), (label, desc) in TE_LABELS.items():
        if lo <= te < hi:
            return label, desc
    return str(te), ""


def _load_context(load):
    if load is None:
        return ""
    for lo, hi, ctx in LOAD_CONTEXT:
        if lo <= load < hi:
            return ctx
    return ""


def generate_activity(act_row, health_row):
    """Generate markdown for a single activity. Returns the markdown string."""
    (act_id, act_date, start_time, act_type, dur, dist, avg_hr, max_hr,
     cals, ae, an, load, z1, z2, z3, z4, z5) = act_row

    day_str  = datetime.fromisoformat(str(act_date)).strftime("%A, %B %d %Y")
    type_str = (act_type or "workout").replace("_", " ").title()
    time_str = datetime.fromisoformat(str(start_time)).strftime("%H:%M") if start_time else "—"

    lines = []
    a = lines.append

    a(f"# {type_str} — {day_str}")
    a("")
    a(f"_Started: {time_str} · Activity ID: {act_id}_")
    a("")
    a("---")
    a("")

    # ── Key Metrics ───────────────────────────────────────────────────────────
    a("## Key Metrics")
    a("")
    a("| Metric | Value |")
    a("|--------|-------|")
    a(f"| Duration | {_fmt(dur, 0)} min |")
    if dist:
        a(f"| Distance | {_fmt(dist, 2)} km |")
        if dur:
            pace = dur / dist
            pace_m, pace_s = int(pace), int((pace % 1) * 60)
            a(f"| Avg Pace | {pace_m}:{pace_s:02d} min/km |")
    a(f"| Avg Heart Rate | {_fmt(avg_hr, 0)} bpm |")
    a(f"| Max Heart Rate | {_fmt(max_hr, 0)} bpm |")
    a(f"| Calories Burned | {_fmt(cals, 0)} kcal |")
    a(f"| Training Load | {_fmt(load, 0)} — {_load_context(load)} |")
    a("")

    # ── Training Effect ───────────────────────────────────────────────────────
    a("## Training Effect")
    a("")
    a("Training Effect (TE) measures how much a session stimulates fitness adaptation. Scale: 1.0–5.0+")
    a("")
    ae_label, ae_desc = _te_info(ae)
    an_label, an_desc = _te_info(an)
    a(f"| Effect | Score | Level | Meaning |")
    a(f"|--------|-------|-------|---------|")
    a(f"| Aerobic | {_fmt(ae, 1)} | {ae_label} | {ae_desc} |")
    a(f"| Anaerobic | {_fmt(an, 1)} | {an_label} | {an_desc} |")
    a("")

    if ae is not None:
        a("**Aerobic TE** = how much this session builds your endurance and aerobic capacity.")
        if ae >= 4.0:
            a(f"TE {ae:.1f} is in the 'Highly Improving' range — this was a genuinely hard session. Expect fatigue for 24–48 h and meaningful aerobic adaptation over the following days.")
        elif ae >= 3.0:
            a(f"TE {ae:.1f} is the sweet spot for building fitness. Stimulus is high enough to drive adaptation without excessive fatigue.")
        elif ae >= 2.0:
            a(f"TE {ae:.1f} is a maintenance session. Keeps current fitness, won't build it. Good choice on days when recovery is a priority.")
        else:
            a(f"TE {ae:.1f} is essentially a recovery activity.")
        a("")

    if an is not None and an >= 1.5:
        a("**Anaerobic TE** = how much this session trains your lactate system and speed.")
        if an >= 3.0:
            a(f"TE {an:.1f} — you hit meaningful higher-intensity work, training your lactate threshold and top-end speed.")
        else:
            a(f"TE {an:.1f} — minor anaerobic demand; this was primarily an aerobic session with some harder moments.")
        a("")

    # ── Heart Rate Analysis ───────────────────────────────────────────────────
    a("## Heart Rate Analysis")
    a("")
    if avg_hr and max_hr:
        a(f"**Avg HR:** {avg_hr} bpm · **Max HR:** {max_hr} bpm")
        a("")
        ratio = avg_hr / max_hr
        if ratio >= 0.90:
            effort = "near-maximal effort throughout. Very high intensity."
        elif ratio >= 0.80:
            effort = "hard effort. Significant time in lactate threshold / VO2max territory."
        elif ratio >= 0.70:
            effort = "moderate-to-hard effort. Good mix of aerobic and threshold work."
        elif ratio >= 0.60:
            effort = "moderate effort. Mostly aerobic, some drift toward harder zones."
        else:
            effort = "easy effort. Primarily Zone 1–2 aerobic work."
        a(f"Avg/max ratio: {ratio:.0%} — {effort}")
        a("")

    zones = [z1, z2, z3, z4, z5]
    if any(z is not None for z in zones):
        a("### HR Zone Breakdown")
        a("")
        a("| Zone | Description | Range | Time in Zone | % of Session |")
        a("|------|-------------|-------|-------------|-------------|")
        total_zone_min = sum(z for z in zones if z is not None)
        for i, (z_name, z_range, z_desc) in enumerate(HR_ZONES):
            z_val = zones[i]
            pct = f"{z_val/total_zone_min*100:.0f}%" if z_val and total_zone_min else "—"
            a(f"| {z_name} | {z_desc} | {z_range} | {_fmt(z_val, 0)} min | {pct} |")
        a("")
        # Zone distribution insight
        hard_min = (z4 or 0) + (z5 or 0)
        easy_min = (z1 or 0) + (z2 or 0)
        if hard_min > 10:
            a(f"**{hard_min:.0f} min** in Zone 4–5 — high intensity, significant lactate demand and cardiovascular stress.")
        if easy_min > 15:
            a(f"**{easy_min:.0f} min** in Zone 1–2 — solid base work. This is what builds long-term aerobic efficiency.")
        a("")
    else:
        a("_HR zone data not available for this session (Garmin detail call failed or watch didn't track zones)._")
        a("")

    # ── Recovery Context ──────────────────────────────────────────────────────
    a("## Recovery Impact")
    a("")
    if health_row:
        rec_hrs = health_row.get("recovery_time_hours")
        next_readiness = health_row.get("training_readiness_score")
        next_level     = health_row.get("training_readiness_level")
        next_hrv       = health_row.get("hrv_last_night")
        next_bb        = health_row.get("bb_end")

        if rec_hrs and rec_hrs < 200:
            a(f"**Recovery time:** {rec_hrs} h — Garmin's estimate until full readiness returns.")
        if next_readiness:
            a(f"**Next day readiness:** {next_readiness} ({next_level or '—'})")
        if next_hrv:
            a(f"**Next morning HRV:** {next_hrv:.0f} ms")
        if next_bb:
            a(f"**Next day Body Battery end:** {next_bb}")

        if next_readiness and next_readiness < 50:
            a("")
            a("Readiness dropped below 50 — the body is asking for an easy day or rest. Avoid hard sessions until readiness rebounds.")
        elif next_readiness and next_readiness >= 75:
            a("")
            a("Readiness stayed high despite the session — good sign of recovery capacity.")
    else:
        a("_No next-day health data available yet. Sync tomorrow to see recovery impact._")
    a("")

    # ── How It Fits ───────────────────────────────────────────────────────────
    a("## Context")
    a("")
    if ae and ae >= 4.0 and load and load >= 100:
        a(
            f"This was a high-stimulus session (TE {ae:.1f}, load {load:.0f}). "
            "Follow-up with easy activity or rest for 24–48 h to allow adaptation. "
            "The fitness gain happens during recovery, not during the run."
        )
    elif ae and ae >= 3.0:
        a(
            f"A productive aerobic session (TE {ae:.1f}). "
            "Standard recovery (overnight sleep + easy next day) is sufficient before the next hard effort."
        )
    else:
        a("Easy to moderate session — recovery demand is low. Can train again tomorrow if readiness allows.")
    a("")

    # ── Raw Data ──────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Raw Data")
    a("")
    raw = {
        "activity_id":   act_id,
        "date":          str(act_date),
        "start_time":    str(start_time),
        "activity_type": act_type,
        "duration_min":  dur,
        "distance_km":   dist,
        "avg_hr":        avg_hr,
        "max_hr":        max_hr,
        "calories":      cals,
        "training_effect_aerobic":   ae,
        "training_effect_anaerobic": an,
        "training_load": load,
        "hr_zone1_min":  z1,
        "hr_zone2_min":  z2,
        "hr_zone3_min":  z3,
        "hr_zone4_min":  z4,
        "hr_zone5_min":  z5,
    }
    non_null = {k: v for k, v in raw.items() if v is not None}
    a("```json")
    a(json.dumps(non_null, indent=2, default=str))
    a("```")
    if health_row:
        a("")
        a("**Next-day health snapshot:**")
        a("")
        snap = {k: v for k, v in health_row.items() if v is not None}
        a("```json")
        a(json.dumps(snap, indent=2, default=str))
        a("```")
    a("")
    a("---")
    a(f"_Generated by `scripts/generate_activities.py`_")

    return "\n".join(lines)


def generate(target_date=None, regenerate_all=False):
    con = _conn()

    query = """
        SELECT activity_id, date, start_time, activity_type,
               duration_min, distance_km, avg_hr, max_hr,
               calories, training_effect_aerobic, training_effect_anaerobic,
               training_load, hr_zone1_min, hr_zone2_min, hr_zone3_min,
               hr_zone4_min, hr_zone5_min
        FROM health_activities
    """
    params = []
    if target_date:
        query += " WHERE date = ?"
        params.append(target_date)
    query += " ORDER BY date DESC, start_time DESC"

    activities = con.execute(query, params).fetchall()

    if not activities:
        print("No activities found.")
        return

    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    for act in activities:
        act_id, act_date = act[0], act[1]
        act_type = (act[3] or "workout").replace("/", "-").lower()
        filename = f"{act_date}-{act_type}.md"
        output   = ACTIVITIES_DIR / filename

        if output.exists() and not regenerate_all:
            print(f"  skip (exists): {filename}")
            continue

        # Next-day health data for recovery context
        next_date = (datetime.fromisoformat(str(act_date)) + __import__("datetime").timedelta(days=1)).date().isoformat()
        health_cols = [
            "date","sleep_score","sleep_qualifier","sleep_total_min",
            "hrv_last_night","rhr","bb_max","bb_min","bb_end","stress_avg",
            "training_readiness_score","training_readiness_level",
            "recovery_time_hours","endurance_score","fitness_age",
        ]
        health_row_raw = con.execute(
            f"SELECT {', '.join(health_cols)} FROM health_days WHERE date = ?", [next_date]
        ).fetchone()
        health_row = dict(zip(health_cols, health_row_raw)) if health_row_raw else None
        if health_row:
            health_row = {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in health_row.items() if v is not None}

        md = generate_activity(act, health_row)
        output.write_text(md)
        print(f"  written: {filename}")
        written += 1

    print(f"Done — {written} file(s) written, {len(activities) - written} skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Generate for a specific date (YYYY-MM-DD)")
    parser.add_argument("--all", dest="regenerate_all", action="store_true", help="Regenerate all")
    args = parser.parse_args()
    generate(args.date, args.regenerate_all)
