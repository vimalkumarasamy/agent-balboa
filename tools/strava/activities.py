"""
Strava activity tools for the agent.
All reads use local synced data. Falls back to live API only if not synced.
"""

import requests
from typing import Optional
from tools.strava.auth import get_access_token
from tools.strava.sync import get_local_activities, needs_initial_sync
from tools.strava.analytics import compute_prs, weekly_mileage, activity_type_breakdown

API_BASE = "https://www.strava.com/api/v3"


def get_recent_activities(count: int = 20) -> list[dict]:
    """Fetch the most recent Strava activities from local storage. Returns activities
    with name, type, distance (km), moving time, elevation gain, pace, and date."""
    if needs_initial_sync():
        # Fall back to live API if not yet synced
        token = get_access_token()
        resp = requests.get(
            f"{API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": count},
        )
        resp.raise_for_status()
        activities = resp.json()
        return [
            {
                "id": a["id"],
                "name": a.get("name"),
                "type": a.get("type"),
                "date": a.get("start_date_local", "")[:10],
                "distance_km": round(a.get("distance", 0) / 1000, 2),
                "moving_time_min": round(a.get("moving_time", 0) / 60, 1),
                "elevation_gain_m": a.get("total_elevation_gain"),
                "kudos": a.get("kudos_count", 0),
            }
            for a in activities
        ]

    return get_local_activities(days=90)[:count]


def get_best_efforts(force_refresh: bool = False) -> dict:
    """Get your all-time personal records computed from local activity data.
    Covers race-distance PRs (5K, 10K, half marathon, marathon, 50K etc).
    Pass force_refresh=True to recompute from scratch."""
    return compute_prs()


def get_training_summary(weeks: int = 8) -> dict:
    """Get a weekly training summary for the last N weeks including mileage,
    run count, and activity type breakdown. Useful for understanding training load."""
    return {
        "weekly_mileage": weekly_mileage(weeks=weeks),
        "activity_breakdown_last_year": activity_type_breakdown(days=365),
    }


def get_athlete_profile() -> dict:
    """Fetch your Strava athlete profile including name, city, and fitness stats."""
    token = get_access_token()
    resp = requests.get(
        f"{API_BASE}/athlete",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    a = resp.json()
    return {
        "name": f"{a.get('firstname')} {a.get('lastname')}",
        "city": a.get("city"),
        "country": a.get("country"),
        "ytd_run_totals": a.get("ytd_run_totals"),
        "all_run_totals": a.get("all_run_totals"),
    }
