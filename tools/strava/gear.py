import requests
from tools.strava.auth import get_access_token

API_BASE = "https://www.strava.com/api/v3"
WORN_OUT_KM = 800  # ~500 miles


def get_shoes() -> list[dict]:
    """Fetch all shoes/gear from your Strava profile with total distance logged.
    Flags shoes that are worn out (over 800km / ~500 miles). Use this to check
    which shoes need replacing."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    athlete = requests.get(f"{API_BASE}/athlete", headers=headers).json()
    shoes_raw = athlete.get("shoes", [])

    if not shoes_raw:
        return [{"message": "No shoes found on your Strava profile. Add gear at strava.com/settings/gear"}]

    shoes = []
    for s in shoes_raw:
        gear = requests.get(f"{API_BASE}/gear/{s['id']}", headers=headers).json()
        distance_km = round(gear.get("distance", 0) / 1000, 1)
        distance_miles = round(distance_km * 0.621371, 1)
        worn_out = distance_km >= WORN_OUT_KM
        shoes.append({
            "name": gear.get("name") or gear.get("model_name", "Unknown"),
            "brand": gear.get("brand_name", "Unknown"),
            "model": gear.get("model_name", ""),
            "distance_km": distance_km,
            "distance_miles": distance_miles,
            "worn_out": worn_out,
            "primary": gear.get("primary", False),
            "status": f"{'WORN OUT' if worn_out else 'OK'} ({distance_miles} miles / {distance_km} km)",
        })

    shoes.sort(key=lambda x: x["distance_km"], reverse=True)
    return shoes
