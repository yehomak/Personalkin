import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

MONGO_URI = os.environ["MYCALENDAR_MONGO_URI"]

_client: MongoClient | None = None


def _db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client["mycalendar"]


def _category_map() -> dict[str, str]:
    cats = _db().categories.find({}, {"id": 1, "name": 1, "_id": 0})
    return {c["id"]: c["name"] for c in cats}


def _fmt(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.strftime("%H:%M")


def get_upcoming_events(days: int = 7) -> str:
    """
    Events from now through the next N days, in chronological order.
    Times are UTC. All-day events show no time.
    """
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    cats = _category_map()

    cursor = _db().events.find(
        {"startAt": {"$gte": now.isoformat(), "$lte": until.isoformat()}},
        {"_id": 0, "userId": 0, "googleEventId": 0, "pendingSync": 0, "color": 0},
        sort=[("startAt", 1)],
    )

    events = []
    for e in cursor:
        events.append({
            "title": e["title"],
            "date": e["startAt"][:10],
            "time": None if e.get("allDay") else _fmt(e["startAt"]),
            "end_time": None if e.get("allDay") else _fmt(e["endAt"]),
            "all_day": e.get("allDay", False),
            "category": cats.get(e.get("categoryId", ""), ""),
            "description": e.get("description", ""),
        })

    return json.dumps({"days": days, "count": len(events), "events": events}, indent=2)


def create_event(
    title: str,
    date: str,
    start_time: str | None = None,
    end_time: str | None = None,
    duration_min: int | None = None,
    category: str | None = None,
    all_day: bool = False,
    notes: str = "",
) -> str:
    """
    Create a new event in MyCalendar.
    date: YYYY-MM-DD
    start_time / end_time: HH:MM in UTC
    duration_min: alternative to end_time (minutes)
    category: category name, e.g. "Travel", "Work", "Body", "Life"
    notes: stored as description
    """
    db = _db()

    sample = db.events.find_one({}, {"userId": 1})
    if not sample:
        return json.dumps({"error": "no existing events — cannot determine userId"})
    user_id = sample["userId"]

    cat_id = None
    if category:
        name_to_id = {v: k for k, v in _category_map().items()}
        cat_id = name_to_id.get(category)
        if not cat_id:
            return json.dumps({"error": f"unknown category '{category}'. available: {sorted(name_to_id)}"})

    if all_day:
        start_at = f"{date}T00:00:00+00:00"
        end_at = f"{date}T00:00:00+00:00"
    else:
        if not start_time:
            return json.dumps({"error": "start_time required for timed events (HH:MM UTC)"})
        start_at = f"{date}T{start_time}:00+00:00"
        if end_time:
            end_at = f"{date}T{end_time}:00+00:00"
        elif duration_min:
            dt = datetime.fromisoformat(start_at)
            end_at = (dt + timedelta(minutes=duration_min)).isoformat()
        else:
            return json.dumps({"error": "provide end_time or duration_min"})

    event = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "title": title,
        "startAt": start_at,
        "endAt": end_at,
        "allDay": all_day,
        "categoryId": cat_id,
        "color": None,
        "pendingSync": False,
        "description": notes,
    }
    db.events.insert_one(event)

    return json.dumps({
        "created": True,
        "id": event["id"],
        "title": title,
        "date": date,
        "start_utc": start_at,
        "end_utc": end_at,
        "category": category,
        "notes": notes,
    }, indent=2)


def get_events_on_date(date: str) -> str:
    """
    All events on a specific date (YYYY-MM-DD). Times are UTC.
    """
    day_start = datetime.fromisoformat(f"{date}T00:00:00+00:00")
    day_end = day_start + timedelta(days=1)
    cats = _category_map()

    cursor = _db().events.find(
        {"startAt": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}},
        {"_id": 0, "userId": 0, "googleEventId": 0, "pendingSync": 0, "color": 0},
        sort=[("startAt", 1)],
    )

    events = []
    for e in cursor:
        events.append({
            "title": e["title"],
            "time": None if e.get("allDay") else _fmt(e["startAt"]),
            "end_time": None if e.get("allDay") else _fmt(e["endAt"]),
            "all_day": e.get("allDay", False),
            "category": cats.get(e.get("categoryId", ""), ""),
            "description": e.get("description", ""),
        })

    return json.dumps({"date": date, "count": len(events), "events": events}, indent=2)
