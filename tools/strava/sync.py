import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional
from tools.strava.auth import get_access_token

API_BASE = "https://www.strava.com/api/v3"
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
ACTIVITIES_DIR = os.path.join(DATA_DIR, "activities")
META_PATH = os.path.join(DATA_DIR, "meta.json")
INCREMENTAL_THRESHOLD_HOURS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_meta() -> dict:
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            return json.load(f)
    return {}


def _save_meta(meta: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def _year_path(year: int) -> str:
    return os.path.join(ACTIVITIES_DIR, f"{year}.json")


def _load_year(year: int) -> list:
    path = _year_path(year)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_year(year: int, activities: list):
    os.makedirs(ACTIVITIES_DIR, exist_ok=True)
    activities.sort(key=lambda a: a.get("date", ""), reverse=True)
    with open(_year_path(year), "w") as f:
        json.dump(activities, f, indent=2)


def _shape(raw: dict) -> dict:
    distance_m = raw.get("distance", 0)
    distance_km = round(distance_m / 1000, 2)
    moving_time_s = raw.get("moving_time", 0)
    pace = round((moving_time_s / 60) / distance_km, 2) if distance_km > 0 else None
    return {
        "id": raw["id"],
        "date": raw.get("start_date_local", "")[:10],
        "start_datetime": raw.get("start_date_local", ""),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "sport_type": raw.get("sport_type"),
        "distance_km": distance_km,
        "moving_time_s": moving_time_s,
        "elapsed_time_s": raw.get("elapsed_time"),
        "elevation_gain_m": raw.get("total_elevation_gain"),
        "avg_speed_ms": raw.get("average_speed"),
        "max_speed_ms": raw.get("max_speed"),
        "pace_min_per_km": pace,
        "avg_heartrate": raw.get("average_heartrate"),
        "max_heartrate": raw.get("max_heartrate"),
        "avg_cadence": raw.get("average_cadence"),
        "suffer_score": raw.get("suffer_score"),
        "avg_watts": raw.get("average_watts"),
        "gear_id": raw.get("gear_id"),
        "kudos_count": raw.get("kudos_count", 0),
        "workout_type": raw.get("workout_type"),
        "trainer": raw.get("trainer", False),
        "start_latlng": raw.get("start_latlng"),
        "timezone": raw.get("timezone", "").split(" ")[-1].strip(")"),
        "device_name": raw.get("device_name"),
        "pr_count": raw.get("pr_count", 0),
        "achievement_count": raw.get("achievement_count", 0),
    }


def _fetch_all_since(token: str, after_ts: int = None, progress_callback=None) -> list:
    """Paginate Strava API and return all activities, optionally filtered by after_ts."""
    all_activities = []
    page = 1
    while True:
        if progress_callback:
            progress_callback(f"  Fetching page {page} ({len(all_activities)} activities so far)...")
        params = {"per_page": 200, "page": page}
        if after_ts:
            params["after"] = after_ts
        resp = requests.get(
            f"{API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_activities.extend(batch)
        page += 1
    return all_activities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def needs_initial_sync() -> bool:
    return not os.path.exists(META_PATH)


def needs_incremental_sync() -> bool:
    meta = _load_meta()
    last_sync = meta.get("last_sync")
    if not last_sync:
        return True
    return datetime.now() - datetime.fromisoformat(last_sync) > timedelta(hours=INCREMENTAL_THRESHOLD_HOURS)


def run_initial_sync(progress_callback=None) -> int:
    """Fetch ALL historical activities and store by year. Returns total count."""
    token = get_access_token()

    if progress_callback:
        progress_callback("  Fetching your full Strava history (all time)...")

    raw_activities = _fetch_all_since(token, progress_callback=progress_callback)

    # Group by year
    by_year: dict[int, list] = {}
    for raw in raw_activities:
        activity = _shape(raw)
        year = int(activity["date"][:4]) if activity.get("date") else datetime.now().year
        by_year.setdefault(year, []).append(activity)

    for year, activities in by_year.items():
        _save_year(year, activities)

    # Save metadata
    athlete = requests.get(
        f"{API_BASE}/athlete",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    total = sum(len(v) for v in by_year.values())
    meta = {
        "last_sync": datetime.now().isoformat(),
        "athlete_id": athlete.get("id"),
        "athlete_name": f"{athlete.get('firstname')} {athlete.get('lastname')}",
        "years": sorted(by_year.keys()),
        "total_activities": total,
        "activities_per_year": {str(y): len(a) for y, a in sorted(by_year.items())},
    }
    _save_meta(meta)

    if progress_callback:
        progress_callback(f"  Saved {total} activities across {len(by_year)} years.")

    return total


def run_incremental_sync(progress_callback=None) -> int:
    """Fetch only new activities since last sync and append to appropriate year files."""
    meta = _load_meta()
    if not meta:
        return run_initial_sync(progress_callback)

    last_sync = meta.get("last_sync")
    after_ts = int(datetime.fromisoformat(last_sync).timestamp()) - 3600  # 1hr overlap

    token = get_access_token()
    raw_new = _fetch_all_since(token, after_ts=after_ts)

    if not raw_new:
        meta["last_sync"] = datetime.now().isoformat()
        _save_meta(meta)
        return 0

    # Load existing IDs to avoid duplicates
    current_year = datetime.now().year
    affected_years = set()
    new_by_year: dict[int, list] = {}

    for raw in raw_new:
        activity = _shape(raw)
        year = int(activity["date"][:4]) if activity.get("date") else current_year
        new_by_year.setdefault(year, []).append(activity)
        affected_years.add(year)

    added = 0
    for year, new_activities in new_by_year.items():
        existing = _load_year(year)
        existing_ids = {a["id"] for a in existing}
        truly_new = [a for a in new_activities if a["id"] not in existing_ids]
        if truly_new:
            _save_year(year, existing + truly_new)
            added += len(truly_new)

    # Update meta
    meta["last_sync"] = datetime.now().isoformat()
    meta["total_activities"] = meta.get("total_activities", 0) + added
    for year in affected_years:
        meta.setdefault("activities_per_year", {})[str(year)] = len(_load_year(year))
    meta["years"] = sorted(set(meta.get("years", []) + list(affected_years)))
    _save_meta(meta)

    return added


def get_local_activities(days: int = 365, activity_type: str = None) -> list[dict]:
    """Load activities from local year files filtered by recency and optional type."""
    if not os.path.exists(ACTIVITIES_DIR):
        return []

    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    cutoff_year = int(cutoff[:4])
    current_year = datetime.now().year

    activities = []
    for year in range(cutoff_year, current_year + 1):
        for a in _load_year(year):
            if a.get("date", "") >= cutoff:
                activities.append(a)

    if activity_type:
        activities = [a for a in activities if a.get("type", "").lower() == activity_type.lower()]

    activities.sort(key=lambda a: a.get("date", ""), reverse=True)
    return activities


def get_db_stats() -> dict:
    """Return metadata about the local activity database."""
    if not os.path.exists(META_PATH):
        return {"synced": False}
    meta = _load_meta()
    return {
        "synced": True,
        **meta,
        "activities_last_30_days": len(get_local_activities(days=30)),
        "activities_last_year": len(get_local_activities(days=365)),
    }
