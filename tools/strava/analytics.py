"""
Local analytics computed entirely from synced data in data/activities/.
No API calls made here — run sync first.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from tools.strava.sync import get_local_activities, _load_year, _save_year, _load_meta, ACTIVITIES_DIR
from tools.strava.auth import get_access_token

API_BASE = "https://www.strava.com/api/v3"

# Distance ranges (km) for identifying race-distance activities
DISTANCE_RANGES = {
    "400m":          (0.35,  0.45),
    "1K":            (0.90,  1.10),
    "1 mile":        (1.55,  1.70),
    "5K":            (4.80,  5.30),
    "10K":           (9.50, 10.50),
    "Half Marathon": (20.50, 22.00),
    "Marathon":      (41.80, 43.50),
    "50K":           (48.00, 52.00),
}


def _format_time(seconds: int) -> str:
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"


# ---------------------------------------------------------------------------
# PR computation — from race-distance activities (no API needed)
# ---------------------------------------------------------------------------

def compute_prs_from_races() -> dict:
    """Compute all-time PRs by finding your fastest run at each standard distance.
    Uses only local data — works for standalone races and time trials.
    For best-effort splits within longer runs, use compute_prs_from_best_efforts()."""
    all_runs = get_local_activities(days=365 * 20, activity_type="Run")

    prs = {}
    for name, (lo, hi) in DISTANCE_RANGES.items():
        candidates = [
            a for a in all_runs
            if lo <= a.get("distance_km", 0) <= hi and a.get("moving_time_s", 0) > 0
        ]
        if candidates:
            best = min(candidates, key=lambda a: a["moving_time_s"])
            prs[name] = {
                "time": _format_time(best["moving_time_s"]),
                "date": best["date"],
                "activity_name": best.get("name"),
                "distance_km": best["distance_km"],
                "source": "race",
            }

    return {"personal_records": prs, "source": "local_race_distances"}


# ---------------------------------------------------------------------------
# PR computation — from enriched best_efforts (if enrich has been run)
# ---------------------------------------------------------------------------

def compute_prs_from_best_efforts() -> dict:
    """Compute all-time PRs from stored best_efforts data (requires enrich_best_efforts
    to have been run first). Returns sub-distance PRs like fastest 5K within any run."""
    all_runs = get_local_activities(days=365 * 20, activity_type="Run")
    enriched = [a for a in all_runs if a.get("best_efforts")]

    if not enriched:
        return {"error": "No enriched data found. Run enrich_best_efforts() first."}

    prs = {}
    for activity in enriched:
        for effort in activity.get("best_efforts", []):
            name = effort.get("name")
            elapsed = effort.get("elapsed_time", 0)
            if not name or not elapsed:
                continue
            if name not in prs or elapsed < prs[name]["_elapsed"]:
                prs[name] = {
                    "time": _format_time(elapsed),
                    "date": activity["date"],
                    "activity_name": activity.get("name"),
                    "_elapsed": elapsed,
                    "source": "best_effort",
                }

    for v in prs.values():
        v.pop("_elapsed", None)

    return {"personal_records": prs, "source": "best_efforts", "enriched_runs": len(enriched)}


def compute_prs() -> dict:
    """Compute all-time PRs. Uses best_efforts if enriched data exists,
    otherwise falls back to race-distance matching from local activities."""
    all_runs = get_local_activities(days=365 * 20, activity_type="Run")
    has_enriched = any(a.get("best_efforts") for a in all_runs[:50])

    if has_enriched:
        return compute_prs_from_best_efforts()
    return compute_prs_from_races()


# ---------------------------------------------------------------------------
# Enrichment — fetch best_efforts from Strava API for all runs (one-time)
# ---------------------------------------------------------------------------

def enrich_best_efforts(progress_callback=None):
    """Fetch best_efforts and per-km splits for every Run in local storage.
    Makes one API call per run — respects Strava's 200 req/15min rate limit.
    Safe to interrupt and re-run — skips already-enriched activities."""
    meta = _load_meta()
    if not meta:
        return {"error": "No local data. Run initial sync first."}

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    years = sorted(meta.get("years", []))

    total_enriched = 0
    request_count = 0
    window_start = time.time()

    for year in years:
        activities = _load_year(year)
        modified = False

        for i, activity in enumerate(activities):
            if activity.get("type") != "Run":
                continue
            if activity.get("best_efforts") is not None:
                continue  # already enriched

            # Rate limiting: 200 requests per 15 minutes
            request_count += 1
            if request_count >= 190:
                elapsed = time.time() - window_start
                if elapsed < 900:
                    wait = 900 - elapsed + 5
                    if progress_callback:
                        progress_callback(f"  Rate limit pause: waiting {int(wait)}s...")
                    time.sleep(wait)
                request_count = 0
                window_start = time.time()

            try:
                detail = requests.get(
                    f"{API_BASE}/activities/{activity['id']}",
                    headers=headers,
                    timeout=10,
                ).json()

                activities[i]["best_efforts"] = [
                    {
                        "name": e.get("name"),
                        "elapsed_time": e.get("elapsed_time"),
                        "pr_rank": e.get("pr_rank"),
                    }
                    for e in detail.get("best_efforts", [])
                ]
                activities[i]["splits_metric"] = detail.get("splits_metric", [])
                modified = True
                total_enriched += 1

                if progress_callback and total_enriched % 50 == 0:
                    progress_callback(f"  Enriched {total_enriched} runs so far ({year})...")

            except Exception as e:
                if progress_callback:
                    progress_callback(f"  Skipped activity {activity['id']}: {e}")

        if modified:
            _save_year(year, activities)

    return {"enriched": total_enriched}


# ---------------------------------------------------------------------------
# Training analytics
# ---------------------------------------------------------------------------

def weekly_mileage(weeks: int = 12) -> list[dict]:
    """Return weekly run mileage for the last N weeks from local data."""
    runs = get_local_activities(days=weeks * 7, activity_type="Run")
    today = datetime.now().date()

    weeks_data = []
    for w in range(weeks):
        week_end = today - timedelta(days=w * 7)
        week_start = week_end - timedelta(days=6)
        week_runs = [
            r for r in runs
            if week_start.isoformat() <= r.get("date", "") <= week_end.isoformat()
        ]
        total_km = round(sum(r.get("distance_km", 0) for r in week_runs), 1)
        weeks_data.append({
            "week_of": week_start.isoformat(),
            "runs": len(week_runs),
            "total_km": total_km,
            "avg_heartrate": round(
                sum(r["avg_heartrate"] for r in week_runs if r.get("avg_heartrate")) /
                max(1, sum(1 for r in week_runs if r.get("avg_heartrate"))), 1
            ) or None,
        })

    return list(reversed(weeks_data))


def activity_type_breakdown(days: int = 365) -> dict:
    """Return count and total time by activity type for the last N days."""
    activities = get_local_activities(days=days)
    breakdown = {}
    for a in activities:
        t = a.get("type", "Unknown")
        breakdown.setdefault(t, {"count": 0, "total_hours": 0.0})
        breakdown[t]["count"] += 1
        breakdown[t]["total_hours"] += round(a.get("moving_time_s", 0) / 3600, 2)
    for v in breakdown.values():
        v["total_hours"] = round(v["total_hours"], 1)
    return dict(sorted(breakdown.items(), key=lambda x: x[1]["count"], reverse=True))
