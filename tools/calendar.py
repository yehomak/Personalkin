import os
import json
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
