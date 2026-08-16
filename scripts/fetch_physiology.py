#!/usr/bin/env python3
"""
Fetch physiological profile from Garmin API and save to context/health/physiology.json.

  python scripts/fetch_physiology.py

Pulls: user profile (age, weight, height), race time predictions, personal records.
Saves a JSON file that generate_profile.py and reports can load for personalized context.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

GARMIN_SYNC = Path(os.environ.get("GARMIN_SYNC", Path.home() / "Projects/garmin-sync"))
PERSONALKIN = Path(os.environ.get("PERSONALKIN", Path(__file__).parent.parent))
OUTPUT      = PERSONALKIN / "context" / "health" / "physiology.json"

# garmin-sync venv has garminconnect; add both to path
sys.path.insert(0, str(GARMIN_SYNC))
for site in (GARMIN_SYNC / ".venv").glob("lib/python*/site-packages"):
    sys.path.insert(0, str(site))


def _secs_to_time(s: int) -> str:
    if s is None:
        return "—"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _parse_profile(raw: dict) -> dict:
    ud = (raw or {}).get("userData") or {}
    birth = ud.get("birthDate")
    age = None
    if birth:
        try:
            bd = datetime.strptime(birth, "%Y-%m-%d").date()
            today = date.today()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except ValueError:
            pass
    weight_g = ud.get("weight")
    return {
        "gender":     (ud.get("gender") or "").lower() or None,
        "birth_date": birth,
        "age":        age,
        "weight_kg":  round(weight_g / 1000, 1) if weight_g else None,
        "height_cm":  ud.get("height"),
    }


def _parse_race_predictions(raw: dict) -> dict | None:
    if not raw or not raw.get("time5K"):
        return None
    return {
        "5k":            {"seconds": raw["time5K"],           "readable": _secs_to_time(raw["time5K"])},
        "10k":           {"seconds": raw["time10K"],          "readable": _secs_to_time(raw["time10K"])},
        "half_marathon": {"seconds": raw["timeHalfMarathon"], "readable": _secs_to_time(raw["timeHalfMarathon"])},
        "marathon":      {"seconds": raw["timeMarathon"],     "readable": _secs_to_time(raw["timeMarathon"])},
        "as_of":         raw.get("calendarDate"),
    }


PR_TYPE_NAMES = {
    1: "1km", 2: "1mi", 3: "5km", 7: "10km",
    4: "half_marathon", 6: "marathon",
}

def _parse_personal_records(raw: list) -> list:
    out = []
    seen = set()
    for r in (raw or []):
        type_id = r.get("typeId")
        if type_id not in PR_TYPE_NAMES:
            continue
        if (r.get("activityType") or "running") != "running":
            continue
        name = PR_TYPE_NAMES[type_id]
        if name in seen:
            continue
        seen.add(name)
        val_s = r.get("value")
        out.append({
            "distance": name,
            "seconds":  round(val_s) if val_s else None,
            "readable": _secs_to_time(val_s) if val_s else None,
            "activity": r.get("activityName"),
            "date":     (r.get("actStartDateTimeInGMTFormatted") or "")[:10] or None,
        })
    sort_order = {v: i for i, v in enumerate(PR_TYPE_NAMES.values())}
    return sorted(out, key=lambda x: sort_order.get(x["distance"], 99))


def _parse_vo2max(raw: list) -> float | None:
    for item in (raw or []):
        for key in ("vo2MaxPreciseValue", "vo2Max"):
            if item.get(key):
                return item[key]
    return None


def main():
    try:
        from auth import get_client
    except ImportError:
        print(f"Cannot import auth.py — is garmin-sync at {GARMIN_SYNC}?", file=sys.stderr)
        sys.exit(1)

    print("Connecting to Garmin...")
    api = get_client()
    today = date.today().isoformat()

    print("Fetching user profile...")
    profile = {}
    try:
        profile = _parse_profile(api.get_user_profile())
    except Exception as e:
        print(f"  user_profile: {e}")

    print("Fetching race predictions...")
    race_preds = None
    try:
        race_preds = _parse_race_predictions(api.get_race_predictions())
    except Exception as e:
        print(f"  race_predictions: {e}")

    print("Fetching personal records...")
    prs = []
    try:
        prs = _parse_personal_records(api.get_personal_record())
    except Exception as e:
        print(f"  personal_records: {e}")

    print("Fetching VO2 max...")
    vo2_max = None
    try:
        vo2_max = _parse_vo2max(api.get_max_metrics(today))
    except Exception:
        pass

    result = {
        "generated":        today,
        "profile":          profile,
        "vo2_max":          vo2_max,
        "race_predictions": race_preds,
        "personal_records": prs,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2))

    # Print summary
    p = profile
    print(f"\nPhysiology profile saved → {OUTPUT.relative_to(Path.home())}")
    print()
    if p.get("age"):
        print(f"  Age: {p['age']}  |  Gender: {p.get('gender', '—')}  "
              f"|  Weight: {p.get('weight_kg', '—')} kg  |  Height: {p.get('height_cm', '—')} cm")
    if vo2_max:
        print(f"  VO2 max: {vo2_max}")
    if race_preds:
        print(f"  Race predictions:  5k {race_preds['5k']['readable']}  "
              f"10k {race_preds['10k']['readable']}  "
              f"HM {race_preds['half_marathon']['readable']}")
    if prs:
        print(f"  Personal records: " + "  ".join(f"{r['distance']} {r['readable']}" for r in prs[:4]))


if __name__ == "__main__":
    main()
