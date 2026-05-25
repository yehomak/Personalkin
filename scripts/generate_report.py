#!/usr/bin/env python3
"""
Generates a weekly health report in context/health-reports/YYYY-WXX.md.

Usage:
    python scripts/generate_report.py              # current week
    python scripts/generate_report.py --week 2026-W21
"""

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

DB_PATH    = os.environ.get("GARMIN_DB", str(Path.home() / "Projects/garmin-sync/garmin.duckdb"))
REPORTS_DIR    = Path(__file__).parent.parent / "context" / "health" / "reports"
ACTIVITIES_DIR = Path(__file__).parent.parent / "context" / "health" / "activities"

BARS = "▁▂▃▄▅▆▇█"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

TE_LABELS = {
    (0.0, 2.0): "Recovery",
    (2.0, 3.0): "Maintaining",
    (3.0, 4.0): "Improving",
    (4.0, 5.0): "Highly Improving",
    (5.0, 99.):  "Overreaching",
}

HR_ZONE_DESCRIPTIONS = [
    ("Zone 1 — Very Light",  "< 60% max HR", "Recovery pace, fat oxidation. Can hold a full conversation."),
    ("Zone 2 — Light",       "60–70% max HR", "Aerobic base building. The most important zone for endurance. Should be easy and conversational."),
    ("Zone 3 — Moderate",    "70–80% max HR", "Aerobic, tempo pace. Harder to speak full sentences."),
    ("Zone 4 — Hard",        "80–90% max HR", "Lactate threshold. Sustainable for 30–60 min. Breathing is laboured."),
    ("Zone 5 — Maximum",     "90–100% max HR", "VO2max zone. Short intervals only. Cannot sustain more than a few minutes."),
]


def _conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _week_bounds(week_str):
    if week_str:
        monday = datetime.strptime(f"{week_str}-1", "%G-W%V-%u").date()
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _fmt(v, decimals=1, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{decimals}f}{suffix}"
    return f"{v}{suffix}"


def _stat(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None, None, 0
    return min(vals), max(vals), round(sum(vals) / len(vals), 1), len(vals)


def _verdict(value, good, ok, higher_is_better=True):
    if value is None:
        return "—"
    if higher_is_better:
        if value >= good: return "✓"
        if value >= ok:   return "→"
        return "↓"
    else:
        if value <= good: return "✓"
        if value <= ok:   return "→"
        return "↑"


def _bar(value, lo, hi):
    if value is None or hi == lo:
        return "·"
    idx = int((value - lo) / (hi - lo) * (len(BARS) - 1))
    return BARS[max(0, min(len(BARS) - 1, idx))]


def _fmt_time(v):
    if v is None:
        return "—"
    try:
        s = str(v)
        dt = datetime.fromisoformat(s)
        return dt.strftime("%H:%M")
    except Exception:
        return str(v)[:5]


def _te_label(te):
    if te is None:
        return "—"
    for (lo, hi), label in TE_LABELS.items():
        if lo <= te < hi:
            return label
    return str(te)


def _narrative(data, activities, bl):
    def vals(key):
        return [d[key] for d in data if d.get(key) is not None]

    def week_avg(key):
        v = vals(key)
        return round(sum(v) / len(v), 1) if v else None

    parts = []

    sleep_avg = week_avg("sleep_score")
    if sleep_avg:
        if sleep_avg >= 85:
            parts.append(f"sleep was solid (avg {sleep_avg:.0f})")
        elif sleep_avg >= 75:
            parts.append(f"sleep was decent (avg {sleep_avg:.0f})")
        else:
            parts.append(f"sleep was below par (avg {sleep_avg:.0f})")

    hrv_vals = vals("hrv_last_night")
    if len(hrv_vals) >= 2:
        diff = hrv_vals[-1] - hrv_vals[0]
        if diff > 5:
            parts.append(f"HRV trended up (+{diff:.0f}ms)")
        elif diff < -5:
            parts.append(f"HRV dropped {abs(diff):.0f}ms by week's end — likely post-training suppression")
        else:
            parts.append(f"HRV was stable around {sum(hrv_vals)/len(hrv_vals):.0f}ms")
    elif hrv_vals:
        parts.append(f"HRV at {hrv_vals[0]:.0f}ms")

    if activities:
        types = list(dict.fromkeys(a[1].replace("_", " ").title() for a in activities if a[1]))
        n = len(activities)
        parts.append(f"{n} workout{'s' if n > 1 else ''} logged ({', '.join(types)})")

    r_pairs = [(str(d["date"]), d.get("training_readiness_score"), d.get("training_readiness_level")) for d in data if d.get("training_readiness_score")]
    if r_pairs:
        avg_r = sum(r for _, r, _ in r_pairs) / len(r_pairs)
        if avg_r >= 90:
            parts.append("readiness was prime throughout")
        elif activities:
            # look for crash: drop from ≥70 to <40 on consecutive data days
            for i in range(1, len(r_pairs)):
                if r_pairs[i][1] < 40 and r_pairs[i-1][1] >= 70:
                    parts.append(f"readiness crashed to {r_pairs[i][1]:.0f} ({(r_pairs[i][2] or '').title()}) post-training — heavy session cost")
                    break

    bb_ends = [d.get("bb_end") for d in data if d.get("bb_end") is not None]
    if len(bb_ends) >= 3:
        depleted = sum(1 for v in bb_ends if v < 30)
        if depleted >= 2:
            parts.append(f"body battery stayed depleted ({depleted}/{len(bb_ends)} days below 30) — accumulated fatigue")

    hrv_statuses = [d.get("hrv_status") for d in data if d.get("hrv_status") and d.get("hrv_status").upper() != "NONE"]
    if hrv_statuses:
        low_count = sum(1 for s in hrv_statuses if s.upper() in ("UNBALANCED", "LOW", "POOR"))
        if low_count >= len(hrv_statuses) / 2:
            parts.append(f"HRV status strained most of the week ({low_count}/{len(hrv_statuses)} days unbalanced/low) — monitor recovery")

    if not parts:
        return "Not enough data this week for a narrative. Sync more days to build the picture."

    sentence = parts[0][0].upper() + parts[0][1:]
    if len(parts) > 1:
        sentence += "; " + "; ".join(parts[1:])
    return sentence + "."


def _trend_table(all_days, key, label, lo, hi, good, ok, higher_is_better=True, decimals=0, suffix=""):
    """Returns a single trend row: label + 7-day bars + avg + verdict."""
    week_vals = [d.get(key) for d in all_days]  # one per day, may be None
    present = [v for v in week_vals if v is not None]
    if not present:
        return None
    bars = "  ".join(_bar(v, lo, hi) if v is not None else "·" for v in week_vals)
    avg_v = round(sum(present) / len(present), decimals)
    verd  = _verdict(avg_v, good, ok, higher_is_better)
    avg_str = _fmt(avg_v, decimals, suffix)
    rng_str = f"{_fmt(min(present), decimals, suffix)}–{_fmt(max(present), decimals, suffix)}" if len(present) > 1 else avg_str
    return f"{label:<24}  {bars}   {avg_str:>9}  {rng_str:>13}  {verd}"


def generate(week_str=None):
    monday, sunday = _week_bounds(week_str)
    week_label = monday.strftime("%G-W%V")
    start, end  = monday.isoformat(), sunday.isoformat()

    con = _conn()

    # Overall baseline (all data before this week)
    baseline = con.execute("""
        SELECT AVG(sleep_score), AVG(sleep_total_min), AVG(hrv_last_night),
               AVG(rhr), AVG(bb_max), AVG(bb_end), AVG(stress_avg),
               AVG(steps), AVG(training_readiness_score)
        FROM health_days
        WHERE (sleep_score IS NOT NULL OR rhr IS NOT NULL OR bb_end IS NOT NULL)
          AND date < ?
    """, [start]).fetchone()
    bl = dict(zip(
        ["sleep_score","sleep_total_min","hrv","rhr","bb_max","bb_end","stress","steps","readiness"],
        [round(v, 1) if v else None for v in baseline]
    ))

    # All 7 days of the week (one row per day, may be empty)
    rows = con.execute("""
        SELECT
            date, sleep_score, sleep_qualifier,
            sleep_total_min, sleep_deep_min, sleep_light_min,
            sleep_rem_min, sleep_awake_min, sleep_spo2_avg, sleep_rr_avg,
            sleep_start, sleep_end,
            hrv_last_night, hrv_weekly_avg, hrv_status,
            hrv_baseline_low, hrv_baseline_high,
            rhr, hr_min, hr_max,
            bb_max, bb_min, bb_end, stress_avg,
            steps, distance_km, calories_active,
            training_readiness_score, training_readiness_level, recovery_time_hours,
            spo2_avg, spo2_min, rr_waking_avg,
            endurance_score, fitness_age,
            floors_up, calories_total, moderate_activity_min, vigorous_activity_min
        FROM health_days
        WHERE date BETWEEN ? AND ?
        ORDER BY date
    """, [start, end]).fetchall()

    cols = [
        "date","sleep_score","sleep_qualifier",
        "sleep_total_min","sleep_deep_min","sleep_light_min",
        "sleep_rem_min","sleep_awake_min","sleep_spo2_avg","sleep_rr_avg",
        "sleep_start","sleep_end",
        "hrv_last_night","hrv_weekly_avg","hrv_status",
        "hrv_baseline_low","hrv_baseline_high",
        "rhr","hr_min","hr_max",
        "bb_max","bb_min","bb_end","stress_avg",
        "steps","distance_km","calories_active",
        "training_readiness_score","training_readiness_level","recovery_time_hours",
        "spo2_avg","spo2_min","rr_waking_avg",
        "endurance_score","fitness_age",
        "floors_up","calories_total","moderate_activity_min","vigorous_activity_min",
    ]
    rows_by_date = {str(r[0]): dict(zip(cols, r)) for r in rows}

    # Build full 7-day list (Mon–Sun), filling missing dates with empty dicts
    all_days = []
    for i in range(7):
        d = (monday + timedelta(days=i)).isoformat()
        all_days.append(rows_by_date.get(d, {"date": d}))

    data = [d for d in all_days if d.get("sleep_score") or d.get("rhr") or d.get("bb_end")]

    # Activities
    activities = con.execute("""
        SELECT date, activity_type, duration_min, distance_km,
               avg_hr, max_hr, calories, training_load,
               training_effect_aerobic, training_effect_anaerobic,
               hr_zone1_min, hr_zone2_min, hr_zone3_min, hr_zone4_min, hr_zone5_min,
               activity_id
        FROM health_activities
        WHERE date BETWEEN ? AND ?
        ORDER BY date, start_time
    """, [start, end]).fetchall()

    def vals(key):
        return [d[key] for d in data if d.get(key) is not None]

    lines = []
    a = lines.append

    a(f"# Weekly Health Report — {week_label}")
    a(f"")
    a(f"_{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')} · {len(data)} day(s) with data_")
    a("")
    a("---")
    a("")

    if not data:
        a("_No health data for this week. Run `sync.py` in garmin-sync._")
    else:
        # ── Summary ───────────────────────────────────────────────────────────
        a("## Summary")
        a("")
        a(_narrative(data, activities, bl))
        a("")

        # ── Trends ────────────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Trends")
        a("")
        day_initials = "  ".join(d[0] for d in DAYS)
        a(f"```")
        a(f"{'Metric':<24}  {day_initials}   {'Avg':>9}  {'Range':>13}  Verdict")
        a(f"{'─'*24}  {'─'*19}   {'─'*9}  {'─'*13}  {'─'*7}")

        trend_rows = [
            _trend_table(all_days, "sleep_score",             "Sleep Score",     50, 100, 85, 70),
            _trend_table(all_days, "hrv_last_night",          "HRV Last Night",  40, 120, 80, 60,  suffix=" ms"),
            _trend_table(all_days, "rhr",                     "Resting HR",      40,  80, 50, 65,  higher_is_better=False, suffix=" bpm"),
            _trend_table(all_days, "bb_end",                  "Body Battery End", 0, 100, 50, 30),
            _trend_table(all_days, "stress_avg",              "Stress Avg",       0, 100, 25, 50,  higher_is_better=False),
            _trend_table(all_days, "training_readiness_score","Readiness",        0, 100, 75, 50),
            _trend_table(all_days, "steps",                   "Steps",         2000,15000,8000,5000, decimals=0),
        ]
        for row in trend_rows:
            if row:
                a(row)

        a(f"```")
        a("")
        a(f"_Bars show relative value within your week range. · = no data for that day._")
        a("")

        # ── Day by Day ────────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Day by Day")
        a("")
        a("| Day | Sleep | Duration | HRV | HRV Status | RHR | BB end | Stress | Readiness |")
        a("|-----|-------|----------|-----|------------|-----|--------|--------|-----------|")
        for d in all_days:
            day_name = datetime.fromisoformat(str(d["date"])).strftime("%a %b %d")
            q = (d.get("sleep_qualifier") or "")[:4].title()
            sleep_str = f"{_fmt(d.get('sleep_score'), 0)} ({q})" if d.get("sleep_score") else "—"
            raw_status = (d.get("hrv_status") or "").upper()
            hrv_status = "—" if not raw_status or raw_status == "NONE" else raw_status.title()
            dur_str = f"{_fmt(d.get('sleep_total_min'), 0)} min" if d.get("sleep_total_min") else "—"
            level = (d.get("training_readiness_level") or "").title()
            a(
                f"| {day_name} "
                f"| {sleep_str} "
                f"| {dur_str} "
                f"| {_fmt(d.get('hrv_last_night'), 0)} ms "
                f"| {hrv_status} "
                f"| {_fmt(d.get('rhr'), 0)} bpm "
                f"| {_fmt(d.get('bb_end'), 0)} "
                f"| {_fmt(d.get('stress_avg'), 0)} "
                f"| {_fmt(d.get('training_readiness_score'), 0)} {level} |"
            )
        a("")

        # ── Sleep Detail ──────────────────────────────────────────────────────
        sleep_days = [d for d in data if d.get("sleep_total_min")]
        if sleep_days:
            a("---")
            a("")
            a("## Sleep Detail")
            a("")
            a("| Day | Bedtime | Wake | Score | Total | Deep | REM | Light | Awake | SpO2 | RR |")
            a("|-----|---------|------|-------|-------|------|-----|-------|-------|------|-----|")
            for d in sleep_days:
                day_name = datetime.fromisoformat(str(d["date"])).strftime("%a %b %d")
                light_min = d.get("sleep_light_min")
                if light_min is None:
                    light_min = (d.get("sleep_total_min") or 0) - (d.get("sleep_deep_min") or 0) - (d.get("sleep_rem_min") or 0)
                a(
                    f"| {day_name} "
                    f"| {_fmt_time(d.get('sleep_start'))} "
                    f"| {_fmt_time(d.get('sleep_end'))} "
                    f"| {_fmt(d.get('sleep_score'), 0)} "
                    f"| {_fmt(d.get('sleep_total_min'), 0)} min "
                    f"| {_fmt(d.get('sleep_deep_min'), 0)} min "
                    f"| {_fmt(d.get('sleep_rem_min'), 0)} min "
                    f"| {_fmt(light_min, 0)} min "
                    f"| {_fmt(d.get('sleep_awake_min'), 0)} min "
                    f"| {_fmt(d.get('sleep_spo2_avg'), 1)}% "
                    f"| {_fmt(d.get('sleep_rr_avg'), 1)} |"
                )

            # Sleep consistency note
            bedtimes = [d.get("sleep_start") for d in sleep_days if d.get("sleep_start")]
            if len(bedtimes) >= 3:
                a("")
                a("_Bedtime consistency matters as much as duration — varying by > 1 h disrupts circadian rhythm._")
            a("")
            a("**Deep sleep target:** 60–90 min — physical repair, growth hormone. Getting more deep than target is a sign of high recovery demand.")
            a("**REM target:** 90–120 min — memory, emotional processing. Below 60 min often means sleep was cut short or disrupted.")
            a("**Awake time:** brief awakenings are normal; > 30 min total signals fragmented sleep.")
            a("")

        # ── Training ──────────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Training")
        a("")
        if activities:
            for act in activities:
                act_date, act_type, dur, dist, avg_hr, max_hr, cals, load, ae, an, z1, z2, z3, z4, z5, act_id = act
                day_name = datetime.fromisoformat(str(act_date)).strftime("%A, %b %d")
                a(f"### {(act_type or 'Workout').replace('_', ' ').title()} — {day_name}")
                a("")
                a("| Metric | Value |")
                a("|--------|-------|")
                a(f"| Duration | {_fmt(dur, 0)} min |")
                if dist:
                    a(f"| Distance | {_fmt(dist, 2)} km |")
                if dist and dur:
                    pace_min_km = dur / dist
                    pace_m = int(pace_min_km)
                    pace_s = int((pace_min_km - pace_m) * 60)
                    a(f"| Avg Pace | {pace_m}:{pace_s:02d} min/km |")
                if avg_hr:
                    a(f"| Avg HR | {_fmt(avg_hr, 0)} bpm |")
                if max_hr:
                    a(f"| Max HR | {_fmt(max_hr, 0)} bpm |")
                if cals:
                    a(f"| Calories | {_fmt(cals, 0)} kcal |")
                if load:
                    a(f"| Training Load | {_fmt(load, 0)} |")
                if ae is not None:
                    a(f"| Aerobic Effect | {_fmt(ae, 1)} — {_te_label(ae)} |")
                if an is not None:
                    a(f"| Anaerobic Effect | {_fmt(an, 1)} — {_te_label(an)} |")
                a("")

                if not avg_hr and not load:
                    a("_HR and training load not recorded — watch may not have been worn or this activity type doesn't capture HR automatically._")
                    a("")

                # Low readiness flag
                day_readiness = None
                for d in data:
                    if str(d.get("date")) == str(act_date):
                        day_readiness = d.get("training_readiness_score")
                        break
                if day_readiness and day_readiness < 50:
                    a(f"⚠️ **Readiness was {day_readiness:.0f} ({(next((d.get('training_readiness_level','') for d in data if str(d.get('date'))==str(act_date)), '') or '').title()}) this morning** — training on low readiness increases injury risk and slows adaptation.")
                    a("")

                # Training Effect explanation
                if ae is not None or (an is not None and an >= 1.5):
                    a("**What these numbers mean:**")
                    a("")
                    if ae is not None:
                        if ae >= 4.0:
                            a(f"- Aerobic TE {ae:.1f} = **Highly Improving** — hard session, significant aerobic stimulus. Needs adequate recovery.")
                        elif ae >= 3.0:
                            a(f"- Aerobic TE {ae:.1f} = **Improving** — solid aerobic work. Good stimulus without overdoing it.")
                        elif ae >= 2.0:
                            a(f"- Aerobic TE {ae:.1f} = **Maintaining** — keeps current fitness but won't build it. Good for recovery days.")
                        else:
                            a(f"- Aerobic TE {ae:.1f} = **Recovery** — very easy effort, minimal training stimulus.")
                    if an is not None and an >= 1.5:
                        if an >= 3.0:
                            a(f"- Anaerobic TE {an:.1f} = **Improving** — meaningful high-intensity work, training your lactate system.")
                        else:
                            a(f"- Anaerobic TE {an:.1f} = **Maintaining** — minor anaerobic demand, mostly aerobic session.")

                if avg_hr and max_hr:
                    a("")
                    a("**Effort context (estimated from HR):**")
                    a("")
                    if avg_hr >= 150:
                        effort = "high-intensity"
                        context = "Sustained high HR — significant cardiovascular demand. Drives both aerobic adaptation and fatigue."
                    elif avg_hr >= 130:
                        effort = "moderate-to-hard"
                        context = "HR in the aerobic-to-threshold range — productive training for aerobic capacity and economy."
                    else:
                        effort = "aerobic/easy"
                        context = "HR stayed mostly aerobic — excellent for base building and fat oxidation without excessive fatigue."
                    a(f"Avg HR {avg_hr} bpm / max {max_hr} bpm → **{effort}** effort.")
                    a(context)

                # HR zones if available
                zones = [z1, z2, z3, z4, z5]
                if any(z is not None for z in zones):
                    a("")
                    a("**HR Zone Breakdown:**")
                    a("")
                    a("| Zone | Range | Time | What it means |")
                    a("|------|-------|------|--------------|")
                    for i, (z_label, z_range, z_desc) in enumerate(HR_ZONE_DESCRIPTIONS):
                        z_val = zones[i]
                        a(f"| {z_label} | {z_range} | {_fmt(z_val, 0)} min | {z_desc} |")
                    if z2 is not None and dur:
                        z2_pct = round(z2 / dur * 100)
                        if z2_pct >= 40:
                            a(f"")
                            a(f"Zone 2 was {z2_pct}% of session time — good aerobic base work.")
                        elif z2_pct <= 15 and (z3 or 0) + (z4 or 0) + (z5 or 0) > dur * 0.5:
                            a(f"")
                            a(f"Zone 2 was only {z2_pct}% — high-intensity session. Good for top-end fitness but pair with easy days.")
                a("")

                # Recovery context
                rec = None
                for d in data:
                    if str(d.get("date")) > str(act_date):
                        if d.get("recovery_time_hours") and d.get("recovery_time_hours") < 200:
                            rec = d.get("recovery_time_hours")
                            break
                if rec:
                    a(f"**Recovery time:** {rec} h — Garmin's estimate of hours until full readiness returns.")
                    a("")

            # Training load context
            total_load = sum(a_[7] for a_ in activities if a_[7])
            if total_load:
                a(f"**Total weekly training load:** {total_load:.0f}")
                a("")
                a("Training load < 100 = easy week; 100–300 = moderate; 300+ = high. This builds over time as you log more sessions.")
                a("")
        else:
            a("_No workouts logged this week._")
            a("")

        # ── Activity Minutes ──────────────────────────────────────────────────
        mod_total = sum(d.get("moderate_activity_min") or 0 for d in data)
        vig_total = sum(d.get("vigorous_activity_min") or 0 for d in data)
        if mod_total or vig_total:
            a("---")
            a("")
            a("## Activity Minutes")
            a("")
            equiv = mod_total + vig_total * 2
            a(f"| Type | This Week | WHO Target/week |")
            a(f"|------|-----------|-----------------|")
            a(f"| Moderate activity | {mod_total:.0f} min | 150 min |")
            a(f"| Vigorous activity | {vig_total:.0f} min | 75 min |")
            a(f"| Combined equivalent | {equiv:.0f} min | 150 min |")
            a("")
            if equiv >= 150:
                a("✓ WHO weekly activity target met.")
            else:
                a(f"→ {150 - equiv:.0f} equivalent minutes short of WHO target.")
            a(f"_Based on {len(data)} day(s) with data — may undercount if early-week days weren't synced._")
            a("")

        # ── Highlights ────────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Highlights")
        a("")

        def best_day(key, fn=max):
            pairs = [(str(d["date"]), d[key]) for d in data if d.get(key) is not None]
            if not pairs:
                return "—", None
            best = fn(pairs, key=lambda x: x[1])
            return datetime.fromisoformat(best[0]).strftime("%a %b %d"), best[1]

        best_sleep_d, best_sleep   = best_day("sleep_score", max)
        worst_sleep_d, worst_sleep = best_day("sleep_score", min)
        best_hrv_d,  best_hrv     = best_day("hrv_last_night", max)
        worst_hrv_d, worst_hrv    = best_day("hrv_last_night", min)
        best_r_d,    best_r       = best_day("training_readiness_score", max)

        if best_sleep:
            a(f"- **Best sleep:** {best_sleep_d} — score {_fmt(best_sleep, 0)}")
        if worst_sleep and worst_sleep_d != best_sleep_d and len(vals("sleep_score")) > 1:
            a(f"- **Lowest sleep:** {worst_sleep_d} — score {_fmt(worst_sleep, 0)}")
        if best_hrv:
            a(f"- **Peak HRV:** {best_hrv_d} — {_fmt(best_hrv, 0)} ms")
        if worst_hrv and len(vals("hrv_last_night")) > 1:
            a(f"- **Lowest HRV:** {worst_hrv_d} — {_fmt(worst_hrv, 0)} ms")
        if best_r:
            best_r_level = next((d.get("training_readiness_level", "") for d in data if d.get("training_readiness_score") == best_r), "")
            a(f"- **Peak readiness:** {best_r_d} — {_fmt(best_r, 0)} {(best_r_level or '').title()}")

        bb_peak = max((d.get("bb_max") for d in data if d.get("bb_max")), default=None)
        bb_floor = min((d.get("bb_min") for d in data if d.get("bb_min")), default=None)
        if bb_peak:
            a(f"- **Body Battery peak:** {_fmt(bb_peak, 0)} · lowest point: {_fmt(bb_floor, 0)}")

        # SpO2 alert
        spo2_min_val = min((d.get("spo2_min") for d in data if d.get("spo2_min")), default=None)
        if spo2_min_val and spo2_min_val < 88:
            spo2_day = next((datetime.fromisoformat(str(d["date"])).strftime("%a %b %d") for d in data if d.get("spo2_min") == spo2_min_val), "")
            a(f"- ⚠️ **Low SpO2:** {spo2_day} — min {spo2_min_val:.0f}% (normal floor ≥88%) — may be sensor movement or sleep-disordered breathing")

        # Fitness markers change
        endurance_vals = vals("endurance_score")
        if len(endurance_vals) > 1:
            delta = endurance_vals[-1] - endurance_vals[0]
            if delta != 0:
                a(f"- **Endurance Score:** {endurance_vals[0]:.0f} → {endurance_vals[-1]:.0f} ({'+' if delta > 0 else ''}{delta:.0f})")
        a("")

        # ── Vs Baseline ───────────────────────────────────────────────────────
        any_baseline = any(v is not None for v in bl.values())
        if any_baseline:
            a("---")
            a("")
            a("## vs Prior Baseline")
            a("")
            a("| Metric | This Week | Baseline | Δ |")
            a("|--------|-----------|----------|---|")

            def bl_row(label, key, bl_key, decimals=0, suffix=""):
                wk_vals = [d[key] for d in data if d.get(key) is not None]
                if not wk_vals:
                    return
                wk_avg = round(sum(wk_vals) / len(wk_vals), decimals)
                bsl = bl.get(bl_key)
                if bsl is None:
                    a(f"| {label} | {_fmt(wk_avg, decimals, suffix)} | — | — |")
                    return
                diff = round(wk_avg - bsl, decimals)
                arrow = "↑" if diff > 0 else "↓"
                a(f"| {label} | {_fmt(wk_avg, decimals, suffix)} | {_fmt(bsl, decimals, suffix)} | {arrow}{abs(diff)}{suffix} |")

            bl_row("Sleep Score",       "sleep_score",             "sleep_score")
            bl_row("Sleep Duration",    "sleep_total_min",         "sleep_total_min", suffix=" min")
            bl_row("HRV Last Night",    "hrv_last_night",          "hrv",    suffix=" ms")
            bl_row("Resting HR",        "rhr",                     "rhr",    suffix=" bpm")
            bl_row("Body Battery End",  "bb_end",                  "bb_end")
            bl_row("Avg Stress",        "stress_avg",              "stress")
            bl_row("Steps",             "steps",                   "steps")
            bl_row("Training Readiness","training_readiness_score","readiness")
            a("")
            bl_days = sum(1 for v in bl.values() if v is not None)
            if bl_days < 5:
                a(f"> _Baseline is still thin ({bl_days} prior metric averages) — comparison will improve over weeks._")
                a("")

    # ── Raw Data ──────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Raw Data")
    a("")
    a("Complete readings for each day this week. All non-null fields.")
    a("")
    for d in all_days:
        day_name = datetime.fromisoformat(str(d["date"])).strftime("%A %b %d")
        non_null = {k: v for k, v in d.items() if v is not None and k != "date"}
        if not non_null:
            a(f"**{day_name}** — no data")
            a("")
            continue
        a(f"**{day_name}**")
        a("")
        sleep_keys = ["sleep_score","sleep_qualifier","sleep_total_min","sleep_deep_min","sleep_rem_min","sleep_awake_min","sleep_spo2_avg","sleep_rr_avg"]
        sleep_parts = [f"{k}={round(non_null[k],1) if isinstance(non_null[k],float) else non_null[k]}" for k in sleep_keys if non_null.get(k) is not None]
        if sleep_parts:
            a("sleep: " + ", ".join(sleep_parts))
        def _raw(keys):
            return [f"{k}={round(non_null[k],1) if isinstance(non_null[k],float) else non_null[k]}" for k in keys if non_null.get(k) is not None]

        hrv_parts = _raw(["hrv_last_night","hrv_weekly_avg","hrv_status"])
        if hrv_parts: a("hrv: " + ", ".join(hrv_parts))
        hr_parts = _raw(["rhr","hr_min","hr_max"])
        if hr_parts: a("hr: " + ", ".join(hr_parts))
        bb_parts = _raw(["bb_max","bb_min","bb_end","stress_avg"])
        if bb_parts: a("bb/stress: " + ", ".join(bb_parts))
        act_parts = _raw(["steps","distance_km","calories_active","calories_total","floors_up","moderate_activity_min","vigorous_activity_min"])
        if act_parts: a("activity: " + ", ".join(act_parts))
        r_parts = _raw(["training_readiness_score","training_readiness_level","recovery_time_hours"])
        if r_parts: a("readiness: " + ", ".join(r_parts))
        fit_parts = _raw(["endurance_score","fitness_age","spo2_avg","spo2_min","rr_waking_avg"])
        if fit_parts: a("fitness/other: " + ", ".join(fit_parts))
        a("")

    if activities:
        a("**Activities this week (raw):**")
        a("")
        act_cols = ["date","activity_type","duration_min","distance_km","avg_hr","max_hr",
                    "calories","training_load","training_effect_aerobic","training_effect_anaerobic",
                    "hr_zone1_min","hr_zone2_min","hr_zone3_min","hr_zone4_min","hr_zone5_min"]
        for act in activities:
            act_dict = dict(zip(act_cols, act[:15]))
            non_null_act = {k: v for k, v in act_dict.items() if v is not None}
            a(json.dumps(non_null_act, default=str))
        a("")

    a("---")
    a(f"_Generated by `scripts/generate_report.py --week {week_label}`_")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORTS_DIR / f"{week_label}.md"
    output.write_text("\n".join(lines))
    print(f"Written: {output} ({len(data)} day(s) with data, {len(activities)} activity/activities)")
    return str(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", help="Week to generate (YYYY-WXX, e.g. 2026-W21)")
    args = parser.parse_args()
    generate(args.week)
