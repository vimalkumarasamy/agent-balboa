"""
Social tools: build top-friends list from kudos history, give daily kudos via clubs.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from tools.strava.auth import get_access_token
from tools.strava.sync import get_local_activities, DATA_DIR

API_BASE = "https://www.strava.com/api/v3"
TOP_FRIENDS_PATH = os.path.join(DATA_DIR, "top_friends.json")
KUDOS_LOG_PATH = os.path.join(DATA_DIR, "kudos_log.json")
MAX_FRIENDS = 100
MAX_KUDOS_PER_DAY = 50
KUDOS_DELAY_SECS = 1.5  # pause between each kudos to stay human-like


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_top_friends() -> list:
    if os.path.exists(TOP_FRIENDS_PATH):
        with open(TOP_FRIENDS_PATH) as f:
            return json.load(f).get("friends", [])
    return []


def _load_kudos_log() -> dict:
    if os.path.exists(KUDOS_LOG_PATH):
        with open(KUDOS_LOG_PATH) as f:
            return json.load(f)
    return {"given": []}


def _save_kudos_log(log: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KUDOS_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def _already_kudosed_today(activity_id: int, log: dict) -> bool:
    today = datetime.now().date().isoformat()
    return any(
        str(e["activity_id"]) == str(activity_id) and e["date"] == today
        for e in log.get("given", [])
    )


def _kudos_given_today(log: dict) -> int:
    today = datetime.now().date().isoformat()
    return sum(1 for e in log.get("given", []) if e.get("date") == today)


# ---------------------------------------------------------------------------
# Build top friends
# ---------------------------------------------------------------------------

MAX_REQUESTS_PER_DAY = 1800  # stay under Strava's 2000/day hard cap


def _scan_kudos(activities: list, headers: dict, progress_callback=None) -> dict:
    """Fetch kudosers for a list of activities. Returns {athlete_id: {...}} dict."""
    athlete_kudos: dict[int, dict] = {}
    request_count = 0
    total_requests = 0
    window_start = time.time()

    for i, activity in enumerate(activities):
        if total_requests >= MAX_REQUESTS_PER_DAY:
            if progress_callback:
                progress_callback(f"  Daily API cap reached after {i} activities — saving partial results.")
            break

        if progress_callback and i % 50 == 0 and i > 0:
            progress_callback(f"  Processed {i}/{len(activities)} activities...")

        # 15-minute window management
        request_count += 1
        total_requests += 1
        if request_count >= 190:
            elapsed = time.time() - window_start
            if elapsed < 900:
                wait = 900 - elapsed + 5
                if progress_callback:
                    progress_callback(f"  Rate limit pause: {int(wait)}s...")
                time.sleep(wait)
            request_count = 0
            window_start = time.time()

        resp = requests.get(
            f"{API_BASE}/activities/{activity['id']}/kudos",
            headers=headers,
            params={"per_page": 200},
        )

        if resp.status_code == 429:
            # Hit rate limit mid-window — wait and retry once
            if progress_callback:
                progress_callback("  429 rate limit — waiting 60s before retrying...")
            time.sleep(60)
            resp = requests.get(
                f"{API_BASE}/activities/{activity['id']}/kudos",
                headers=headers,
                params={"per_page": 200},
            )
            total_requests += 1

        if resp.status_code != 200:
            if progress_callback:
                progress_callback(f"  Skipping activity {activity['id']}: HTTP {resp.status_code}")
            continue

        for kudoser in resp.json():
            aid = kudoser.get("id")
            if not aid:
                continue
            if aid not in athlete_kudos:
                athlete_kudos[aid] = {
                    "athlete_id": aid,
                    "name": f"{kudoser.get('firstname', '')} {kudoser.get('lastname', '')}".strip(),
                    "kudos_given_to_me": 0,
                    "last_kudos_date": activity.get("date", ""),
                }
            athlete_kudos[aid]["kudos_given_to_me"] += 1
            if activity.get("date", "") > athlete_kudos[aid]["last_kudos_date"]:
                athlete_kudos[aid]["last_kudos_date"] = activity.get("date", "")

    return athlete_kudos


def _save_top_friends(athlete_kudos: dict, generated_at: str = None):
    ranked = sorted(athlete_kudos.values(), key=lambda x: x["kudos_given_to_me"], reverse=True)
    top = ranked[:MAX_FRIENDS]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOP_FRIENDS_PATH, "w") as f:
        json.dump({
            "generated_at": generated_at or datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "total_unique_kudosers": len(athlete_kudos),
            "friends": top,
        }, f, indent=2)
    return top


def build_top_friends(progress_callback=None) -> dict:
    """Full scan: fetch kudosers for up to 5 years of activities (stays under Strava's
    1800 req/day cap). Run once to set up, then use update_top_friends() weekly."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    all_activities = get_local_activities(days=365 * 5, activity_type=None)
    kudosed = [a for a in all_activities if a.get("kudos_count", 0) > 0]
    # Cap at MAX_REQUESTS_PER_DAY to avoid exhausting the daily limit
    kudosed = kudosed[:MAX_REQUESTS_PER_DAY]

    if progress_callback:
        progress_callback(f"  Scanning {len(kudosed)} activities with kudos (full scan)...")

    athlete_kudos = _scan_kudos(kudosed, headers, progress_callback)
    top = _save_top_friends(athlete_kudos)

    return {
        "mode": "full",
        "total_unique_kudosers": len(athlete_kudos),
        "top_friends_saved": len(top),
        "top_5_preview": [f"{f['name']} ({f['kudos_given_to_me']} kudos)" for f in top[:5]],
    }


def update_top_friends(progress_callback=None) -> dict:
    """Incremental update: only scan activities newer than the last build,
    merge new kudos counts into existing rankings, re-save. Much faster than full rebuild."""
    if not os.path.exists(TOP_FRIENDS_PATH):
        if progress_callback:
            progress_callback("  No existing data — running full build first...")
        return build_top_friends(progress_callback)

    with open(TOP_FRIENDS_PATH) as f:
        existing = json.load(f)

    last_updated = existing.get("last_updated", existing.get("generated_at", ""))
    last_date = last_updated[:10] if last_updated else "2020-01-01"

    # Load existing kudos counts into working dict
    athlete_kudos: dict[int, dict] = {
        f["athlete_id"]: f.copy() for f in existing.get("friends", [])
    }

    # Find new activities since last update
    all_activities = get_local_activities(days=365 * 10, activity_type=None)
    new_kudosed = [
        a for a in all_activities
        if a.get("kudos_count", 0) > 0 and a.get("date", "") > last_date
    ]

    if not new_kudosed:
        return {"mode": "incremental", "new_activities_scanned": 0, "message": "Already up to date."}

    if progress_callback:
        progress_callback(f"  Scanning {len(new_kudosed)} new activities since {last_date}...")

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    new_kudos = _scan_kudos(new_kudosed, headers, progress_callback)

    # Merge new counts into existing
    for aid, data in new_kudos.items():
        if aid in athlete_kudos:
            athlete_kudos[aid]["kudos_given_to_me"] += data["kudos_given_to_me"]
            if data["last_kudos_date"] > athlete_kudos[aid]["last_kudos_date"]:
                athlete_kudos[aid]["last_kudos_date"] = data["last_kudos_date"]
        else:
            athlete_kudos[aid] = data

    top = _save_top_friends(athlete_kudos, generated_at=existing.get("generated_at"))

    return {
        "mode": "incremental",
        "new_activities_scanned": len(new_kudosed),
        "new_kudosers_found": len(new_kudos),
        "top_friends_saved": len(top),
        "top_5_preview": [f"{f['name']} ({f['kudos_given_to_me']} kudos)" for f in top[:5]],
    }


def get_top_friends(limit: int = 20) -> list:
    """Return your top friends ranked by how many kudos they've given you.
    Run build_top_friends() first to generate this list."""
    friends = _load_top_friends()
    if not friends:
        return [{"message": "No friends data yet. Ask Balboa to build your top friends list."}]
    return friends[:limit]


# ---------------------------------------------------------------------------
# Daily kudos
# ---------------------------------------------------------------------------

def get_my_clubs() -> list:
    """Return all Strava clubs you're a member of."""
    token = get_access_token()
    resp = requests.get(
        f"{API_BASE}/athlete/clubs",
        headers={"Authorization": f"Bearer {token}"},
        params={"per_page": 50},
    )
    resp.raise_for_status()
    return [
        {"id": c["id"], "name": c["name"], "member_count": c.get("member_count")}
        for c in resp.json()
    ]


def run_daily_kudos(dry_run: bool = False) -> dict:
    """Give kudos to recent activities from your top 100 friends via shared clubs.
    Caps at 50 kudos per day. Pass dry_run=True to preview without actually giving kudos.
    Logs all kudos to data/kudos_log.json."""
    top_friend_ids = {f["athlete_id"] for f in _load_top_friends()}
    if not top_friend_ids:
        return {"error": "No top friends list found. Run build_top_friends() first."}

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    log = _load_kudos_log()

    already_today = _kudos_given_today(log)
    remaining_quota = MAX_KUDOS_PER_DAY - already_today
    if remaining_quota <= 0:
        return {"message": f"Already gave {already_today} kudos today (daily cap: {MAX_KUDOS_PER_DAY})."}

    # Get all clubs
    clubs_resp = requests.get(
        f"{API_BASE}/athlete/clubs",
        headers=headers,
        params={"per_page": 50},
    ).json()

    # Collect recent club activities from the last 48h by top friends
    candidates = []
    seen_activity_ids = set()

    for club in clubs_resp:
        club_activities = requests.get(
            f"{API_BASE}/clubs/{club['id']}/activities",
            headers=headers,
            params={"per_page": 200},
        ).json()

        for a in club_activities:
            athlete = a.get("athlete", {})
            athlete_id = athlete.get("id")
            activity_id = a.get("id")

            if not activity_id or activity_id in seen_activity_ids:
                continue
            if athlete_id not in top_friend_ids:
                continue
            if a.get("has_kudoed", False):
                continue
            if _already_kudosed_today(activity_id, log):
                continue

            seen_activity_ids.add(activity_id)
            candidates.append({
                "activity_id": activity_id,
                "athlete_id": athlete_id,
                "athlete_name": f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                "activity_name": a.get("name"),
                "activity_type": a.get("type"),
                "club": club["name"],
            })

    to_kudos = candidates[:remaining_quota]

    if dry_run:
        return {
            "dry_run": True,
            "would_kudos": len(to_kudos),
            "activities": to_kudos,
        }

    given = []
    for item in to_kudos:
        resp = requests.post(
            f"{API_BASE}/activities/{item['activity_id']}/kudos",
            headers=headers,
        )
        if resp.status_code in (200, 201):
            given.append(item)
            log["given"].append({
                "activity_id": item["activity_id"],
                "athlete_id": item["athlete_id"],
                "athlete_name": item["athlete_name"],
                "date": datetime.now().date().isoformat(),
                "timestamp": datetime.now().isoformat(),
            })
            time.sleep(KUDOS_DELAY_SECS)

    log["last_run"] = datetime.now().isoformat()
    _save_kudos_log(log)

    return {
        "kudos_given": len(given),
        "to": [f"{g['athlete_name']} — {g['activity_name']}" for g in given],
        "daily_total": _kudos_given_today(log),
    }
