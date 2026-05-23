#!/usr/bin/env python3
"""
Generates a monthly health report in context/health-reports/YYYY-MM.md.

Usage:
    python scripts/generate_monthly_report.py              # current month
    python scripts/generate_monthly_report.py --month 2026-05
"""

import argparse
import json
import os
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import duckdb

DB_PATH     = os.environ.get("GARMIN_DB", str(Path.home() / "Projects/garmin-sync/garmin.duckdb"))
REPORTS_DIR = Path(__file__).parent.parent / "context" / "health" / "reports"


def _conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _month_bounds(month_str):
    if month_str:
        year, month = int(month_str[:4]), int(month_str[5:7])
    else:
        today = date.today()
        year, month = today.year, today.month
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


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


def generate(month_str=None):
    first_day, last_day = _month_bounds(month_str)
    month_label = first_day.strftime("%Y-%m")
    month_name  = first_day.strftime("%B %Y")
    start, end  = first_day.isoformat(), last_day.isoformat()

    con = _conn()

    # Prior baseline (all data before this month)
    baseline = con.execute("""
        SELECT AVG(sleep_score), AVG(sleep_total_min), AVG(hrv_last_night),
               AVG(rhr), AVG(bb_end), AVG(stress_avg),
               AVG(steps), AVG(training_readiness_score),
               AVG(endurance_score), AVG(fitness_age)
        FROM health_days
        WHERE (sleep_score IS NOT NULL OR rhr IS NOT NULL OR bb_end IS NOT NULL)
          AND date < ?
    """, [start]).fetchone()
    bl = dict(zip(
        ["sleep_score","sleep_total_min","hrv","rhr","bb_end","stress","steps","readiness","endurance","fitness_age"],
        [round(v, 1) if v else None for v in baseline]
    ))

    # Month rows
    rows = con.execute("""
        SELECT date, sleep_score, sleep_qualifier,
               sleep_total_min, sleep_deep_min, sleep_rem_min, sleep_awake_min,
               hrv_last_night, hrv_weekly_avg,
               rhr, bb_max, bb_min, bb_end, stress_avg,
               steps, calories_active,
               training_readiness_score, training_readiness_level,
               endurance_score, fitness_age,
               spo2_avg, sleep_spo2_avg
        FROM health_days
        WHERE date BETWEEN ? AND ?
        ORDER BY date
    """, [start, end]).fetchall()

    cols = [
        "date","sleep_score","sleep_qualifier",
        "sleep_total_min","sleep_deep_min","sleep_rem_min","sleep_awake_min",
        "hrv_last_night","hrv_weekly_avg",
        "rhr","bb_max","bb_min","bb_end","stress_avg",
        "steps","calories_active",
        "training_readiness_score","training_readiness_level",
        "endurance_score","fitness_age",
        "spo2_avg","sleep_spo2_avg",
    ]
    all_rows  = [{k: v for k, v in zip(cols, r)} for r in rows]
    data      = [d for d in all_rows if d.get("sleep_score") or d.get("rhr") or d.get("bb_end")]
    data_dates = {str(d["date"]) for d in data}

    # Activities
    activities = con.execute("""
        SELECT date, activity_type, duration_min, distance_km,
               avg_hr, training_load,
               training_effect_aerobic, training_effect_anaerobic
        FROM health_activities
        WHERE date BETWEEN ? AND ?
        ORDER BY date
    """, [start, end]).fetchall()

    def vals(key):
        return [d[key] for d in data if d.get(key) is not None]

    def month_avg(key):
        v = vals(key)
        return round(sum(v) / len(v), 1) if v else None

    lines = []
    a = lines.append

    a(f"# Monthly Health Report — {month_name}")
    a("")
    a(f"_{first_day.strftime('%b %d')} – {last_day.strftime('%b %d, %Y')} · {len(data)} day(s) with data · {len(activities)} workout(s)_")
    a("")
    a("---")
    a("")

    if not data:
        a("_No health data for this month. Run `sync.py` in garmin-sync._")
    else:
        # ── Month Summary ─────────────────────────────────────────────────────
        a("## Summary")
        a("")
        parts = []

        sleep_avg = month_avg("sleep_score")
        if sleep_avg:
            label = "strong" if sleep_avg >= 85 else ("decent" if sleep_avg >= 75 else "below par")
            parts.append(f"sleep averaged {sleep_avg:.0f} ({label})")

        hrv_vals = vals("hrv_last_night")
        if hrv_vals:
            parts.append(f"HRV averaged {sum(hrv_vals)/len(hrv_vals):.0f}ms")

        if activities:
            act_types = list(dict.fromkeys(a_[1] for a_ in activities if a_[1]))
            parts.append(f"{len(activities)} workouts ({', '.join(act_types[:3])})")

        endurance_vals = vals("endurance_score")
        if len(endurance_vals) >= 2:
            delta = endurance_vals[-1] - endurance_vals[0]
            if delta != 0:
                parts.append(f"endurance score {'improved' if delta > 0 else 'dropped'} by {abs(delta):.0f} ({endurance_vals[0]:.0f} → {endurance_vals[-1]:.0f})")

        if parts:
            sentence = parts[0][0].upper() + parts[0][1:]
            if len(parts) > 1:
                sentence += "; " + "; ".join(parts[1:])
            a(sentence + ".")
        a("")

        # ── Month Metrics ─────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Month Averages")
        a("")
        a("| Metric | Month Avg | vs Prior | Range | Verdict |")
        a("|--------|-----------|----------|-------|---------|")

        def metric_row(label, key, bl_key, good, ok, higher=True, decimals=0, suffix=""):
            mn, mx, avg, n = _stat(vals(key))
            if n == 0:
                return
            bsl = bl.get(bl_key)
            diff_str = "—"
            if bsl is not None and avg is not None:
                diff = round(avg - bsl, decimals)
                arrow = "↑" if diff > 0 else "↓"
                diff_str = f"{arrow}{abs(diff)}{suffix}"
            verd = _verdict(avg, good, ok, higher)
            rng  = f"{_fmt(mn, decimals, suffix)}–{_fmt(mx, decimals, suffix)}" if n > 1 else _fmt(mn, decimals, suffix)
            a(f"| {label} | {_fmt(avg, decimals, suffix)} | {diff_str} | {rng} | {verd} |")

        metric_row("Sleep Score",        "sleep_score",             "sleep_score",   85, 70)
        metric_row("Sleep Duration",     "sleep_total_min",         "sleep_total_min",420,360, suffix=" min")
        metric_row("Deep Sleep",         "sleep_deep_min",          "sleep_total_min", 60, 45, suffix=" min")
        metric_row("REM Sleep",          "sleep_rem_min",           "sleep_total_min", 90, 60, suffix=" min")
        metric_row("HRV Last Night",     "hrv_last_night",          "hrv",           80, 60, suffix=" ms")
        metric_row("Resting HR",         "rhr",                     "rhr",           50, 65, higher=False, suffix=" bpm")
        metric_row("Body Battery End",   "bb_end",                  "bb_end",        50, 30)
        metric_row("Avg Stress",         "stress_avg",              "stress",        25, 50, higher=False)
        metric_row("Steps",              "steps",                   "steps",         8000, 5000)
        metric_row("Training Readiness", "training_readiness_score","readiness",     75, 50)
        a("")

        # ── Fitness Trajectory ────────────────────────────────────────────────
        endurance_vals = vals("endurance_score")
        fitness_vals   = vals("fitness_age")
        if endurance_vals or fitness_vals:
            a("---")
            a("")
            a("## Fitness Trajectory")
            a("")
            a("| Metric | Month Start | Month End | Change |")
            a("|--------|-------------|-----------|--------|")
            if len(endurance_vals) >= 2:
                delta = endurance_vals[-1] - endurance_vals[0]
                a(f"| Endurance Score | {endurance_vals[0]:.0f} | {endurance_vals[-1]:.0f} | {'+' if delta >= 0 else ''}{delta:.0f} |")
            elif endurance_vals:
                a(f"| Endurance Score | — | {endurance_vals[0]:.0f} | — |")
            if len(fitness_vals) >= 2:
                delta = fitness_vals[-1] - fitness_vals[0]
                a(f"| Fitness Age | {fitness_vals[0]:.1f} | {fitness_vals[-1]:.1f} | {'+' if delta >= 0 else ''}{delta:.1f} |")
            elif fitness_vals:
                a(f"| Fitness Age | — | {fitness_vals[0]:.1f} | — |")
            a("")
            a("Endurance Score and Fitness Age respond slowly — meaningful change takes 3–6 weeks of consistent training.")
            a("")

        # ── Training Volume ───────────────────────────────────────────────────
        if activities:
            a("---")
            a("")
            a("## Training Volume")
            a("")
            # Group by type
            by_type = {}
            for act in activities:
                t = act[1] or "unknown"
                if t not in by_type:
                    by_type[t] = {"sessions": 0, "duration": 0, "distance": 0, "load": 0}
                by_type[t]["sessions"] += 1
                by_type[t]["duration"] += act[2] or 0
                by_type[t]["distance"] += act[3] or 0
                by_type[t]["load"]     += act[5] or 0

            a("| Activity | Sessions | Total Time | Total Dist | Total Load |")
            a("|----------|----------|-----------|-----------|-----------|")
            for t, v in sorted(by_type.items(), key=lambda x: -x[1]["sessions"]):
                dist_str = f"{v['distance']:.1f} km" if v["distance"] else "—"
                a(f"| {t.replace('_',' ').title()} | {v['sessions']} | {v['duration']:.0f} min | {dist_str} | {v['load']:.0f} |")

            total_load = sum(a_[5] for a_ in activities if a_[5])
            total_dur  = sum(a_[2] for a_ in activities if a_[2])
            a("")
            a(f"**Month totals:** {len(activities)} sessions · {total_dur:.0f} min training · load {total_load:.0f}")
            a("")

        # ── Week by Week ──────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Week by Week")
        a("")
        a("| Week | Days w/data | Avg Sleep | Avg HRV | Avg RHR | Avg BB | Workouts |")
        a("|------|-------------|-----------|---------|---------|--------|----------|")

        # Get ISO weeks in this month
        weeks_seen = set()
        for d in data:
            wk = datetime.fromisoformat(str(d["date"])).strftime("%G-W%V")
            weeks_seen.add(wk)

        for wk in sorted(weeks_seen):
            wk_data = [d for d in data if datetime.fromisoformat(str(d["date"])).strftime("%G-W%V") == wk]
            wk_acts = [act for act in activities if datetime.fromisoformat(str(act[0])).strftime("%G-W%V") == wk]

            def wk_avg(key):
                v = [d[key] for d in wk_data if d.get(key) is not None]
                return round(sum(v)/len(v), 1) if v else None

            a(
                f"| {wk} "
                f"| {len(wk_data)} "
                f"| {_fmt(wk_avg('sleep_score'), 0)} "
                f"| {_fmt(wk_avg('hrv_last_night'), 0)} ms "
                f"| {_fmt(wk_avg('rhr'), 0)} bpm "
                f"| {_fmt(wk_avg('bb_end'), 0)} "
                f"| {len(wk_acts)} |"
            )
        a("")

        # ── Highlights ────────────────────────────────────────────────────────
        a("---")
        a("")
        a("## Month Highlights")
        a("")

        def best_d(key, fn=max):
            pairs = [(str(d["date"]), d[key]) for d in data if d.get(key) is not None]
            if not pairs:
                return "—", None
            best = fn(pairs, key=lambda x: x[1])
            return datetime.fromisoformat(best[0]).strftime("%b %d"), best[1]

        best_sleep_d,  best_sleep  = best_d("sleep_score", max)
        worst_sleep_d, worst_sleep = best_d("sleep_score", min)
        best_hrv_d,    best_hrv    = best_d("hrv_last_night", max)
        worst_hrv_d,   worst_hrv   = best_d("hrv_last_night", min)
        best_r_d,      best_r      = best_d("training_readiness_score", max)

        if best_sleep:
            a(f"- **Best sleep night:** {best_sleep_d} — score {_fmt(best_sleep, 0)}")
        if worst_sleep and worst_sleep_d != best_sleep_d:
            a(f"- **Lowest sleep night:** {worst_sleep_d} — score {_fmt(worst_sleep, 0)}")
        if best_hrv:
            a(f"- **Peak HRV:** {best_hrv_d} — {_fmt(best_hrv, 0)} ms")
        if worst_hrv and len(vals("hrv_last_night")) > 1:
            a(f"- **Lowest HRV:** {worst_hrv_d} — {_fmt(worst_hrv, 0)} ms")
        if best_r:
            a(f"- **Peak readiness:** {best_r_d} — {_fmt(best_r, 0)}")
        bb_peak = max((d.get("bb_max") for d in data if d.get("bb_max")), default=None)
        if bb_peak:
            a(f"- **Body Battery peak:** {_fmt(bb_peak, 0)}")
        a("")

    # ── Raw Data ──────────────────────────────────────────────────────────────
    a("---")
    a("")
    a("## Raw Data")
    a("")
    a("### Daily Readings")
    a("")
    a("| Date | Sleep | Total | Deep | REM | HRV | RHR | BB end | Stress | Readiness | Endurance |")
    a("|------|-------|-------|------|-----|-----|-----|--------|--------|-----------|-----------|")
    for d in all_rows:
        a(
            f"| {d['date']} "
            f"| {_fmt(d.get('sleep_score'), 0)} "
            f"| {_fmt(d.get('sleep_total_min'), 0)} min "
            f"| {_fmt(d.get('sleep_deep_min'), 0)} min "
            f"| {_fmt(d.get('sleep_rem_min'), 0)} min "
            f"| {_fmt(d.get('hrv_last_night'), 0)} ms "
            f"| {_fmt(d.get('rhr'), 0)} bpm "
            f"| {_fmt(d.get('bb_end'), 0)} "
            f"| {_fmt(d.get('stress_avg'), 0)} "
            f"| {_fmt(d.get('training_readiness_score'), 0)} "
            f"| {_fmt(d.get('endurance_score'), 0)} |"
        )
    a("")

    if activities:
        a("### Activities")
        a("")
        a("| Date | Type | Duration | Distance | Avg HR | Load | Aerobic TE |")
        a("|------|------|----------|----------|--------|------|-----------|")
        for act in activities:
            a(
                f"| {act[0]} "
                f"| {act[1] or '—'} "
                f"| {_fmt(act[2], 0)} min "
                f"| {_fmt(act[3], 2)} km "
                f"| {_fmt(act[4], 0)} bpm "
                f"| {_fmt(act[5], 0)} "
                f"| {_fmt(act[6], 1)} |"
            )
        a("")

    a("---")
    a(f"_Generated by `scripts/generate_monthly_report.py --month {month_label}`_")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORTS_DIR / f"{month_label}.md"
    output.write_text("\n".join(lines))
    print(f"Written: {output} ({len(data)} day(s) with data, {len(activities)} activities)")
    return str(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", help="Month to generate (YYYY-MM, e.g. 2026-05)")
    args = parser.parse_args()
    generate(args.month)
