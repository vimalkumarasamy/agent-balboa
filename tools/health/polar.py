"""
Polar Accesslink v3 implementation.

Setup:
1. Register a developer app at developers.polar.com
2. Add POLAR_CLIENT_ID and POLAR_CLIENT_SECRET to .env
3. Run: python scripts/polar_auth.py
"""
import os
import json
import requests
from datetime import date
from typing import Optional
from tools.health.base import HealthProvider, HealthSnapshot, RecoveryData, SleepData

API_BASE = "https://www.polaraccesslink.com/v3"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
AUTH_URL = "https://flow.polar.com/oauth2/authorization"

TOKEN_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../data/polar_token.json")
)


def _load_token() -> Optional[dict]:
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            return json.load(f)
    return None


def save_token(token: dict):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(token, f, indent=2)


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange OAuth authorization code for access token."""
    client_id = os.getenv("POLAR_CLIENT_ID")
    client_secret = os.getenv("POLAR_CLIENT_SECRET")
    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    resp.raise_for_status()
    return resp.json()


def register_user(access_token: str) -> dict:
    """One-time user registration with Polar Accesslink."""
    resp = requests.post(
        f"{API_BASE}/users",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"member-id": "balboa-user"},
    )
    # 409 = already registered, that's fine
    if resp.status_code not in (200, 201, 409):
        resp.raise_for_status()
    if resp.status_code == 409:
        # Already registered — fetch user id via GET /v3/users/{member-id}
        info = requests.get(
            f"{API_BASE}/users/balboa-user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info.raise_for_status()
        return info.json()
    return resp.json()


class PolarProvider(HealthProvider):
    def is_configured(self) -> bool:
        return bool(os.getenv("POLAR_CLIENT_ID") and _load_token())

    def get_snapshot(self, date_str: Optional[str] = None) -> HealthSnapshot:
        today = date_str or date.today().isoformat()
        token_data = _load_token()
        if not token_data:
            raise RuntimeError("Polar token not found. Run scripts/polar_auth.py first.")

        access_token = token_data["access_token"]
        user_id = token_data["polar_user_id"]
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        recovery = self._get_recovery(user_id, today, headers)
        sleep = self._get_sleep(user_id, today, headers)

        return HealthSnapshot(date=today, source="polar", recovery=recovery, sleep=sleep)

    def _get_recovery(self, user_id: int, date_str: str, headers: dict) -> Optional[RecoveryData]:
        resp = requests.get(
            f"{API_BASE}/users/{user_id}/nightly-recharge/{date_str}",
            headers=headers,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        d = resp.json()

        # Map Polar's ANS + sleep charge (-3 to +3 each) to a 0-100 score
        ans = d.get("ans_charge", 0)
        slp = d.get("sleep_charge", 0)
        score = int(((ans + slp + 6) / 12) * 100)

        label_map = {6: "Excellent", 5: "Good", 4: "Compromised", 3: "Low"}
        label = label_map.get(ans + slp, "Compromised")

        return RecoveryData(
            date=date_str,
            score=score,
            hrv_rmssd_ms=d.get("heart_rate_variability_avg"),
            hrv_score=d.get("hrv_score"),
            breathing_rate_rpm=d.get("breathing_rate_avg"),
            resting_hr_bpm=d.get("heart_rate_avg"),
            readiness_label=label,
        )

    def _get_sleep(self, user_id: int, date_str: str, headers: dict) -> Optional[SleepData]:
        resp = requests.get(
            f"{API_BASE}/users/{user_id}/sleep/{date_str}",
            headers=headers,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        d = resp.json()

        light = d.get("light_sleep", 0)
        deep = d.get("deep_sleep", 0)
        rem = d.get("rem_sleep", 0)
        total = light + deep + rem

        return SleepData(
            date=date_str,
            duration_minutes=total,
            score=d.get("sleep_score"),
            hrv_avg_ms=d.get("hrv_avg"),
            hrv_score=d.get("hrv_score"),
            sleep_start=d.get("sleep_start_time"),
            sleep_end=d.get("sleep_end_time"),
            light_sleep_minutes=light,
            deep_sleep_minutes=deep,
            rem_sleep_minutes=rem,
        )
