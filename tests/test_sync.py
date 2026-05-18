import pytest
from tools.strava.sync import _shape


class TestShape:
    def test_computes_distance_km(self):
        raw = _make_raw(distance=10000)
        assert _shape(raw)["distance_km"] == 10.0

    def test_computes_pace(self):
        raw = _make_raw(distance=5000, moving_time=1500)  # 5km in 25min = 5:00/km
        result = _shape(raw)
        assert result["pace_min_per_km"] == 5.0

    def test_pace_none_when_no_distance(self):
        raw = _make_raw(distance=0, moving_time=3600)
        assert _shape(raw)["pace_min_per_km"] is None

    def test_extracts_date_from_local_datetime(self):
        raw = _make_raw(start_date_local="2026-05-16T07:17:02Z")
        assert _shape(raw)["date"] == "2026-05-16"

    def test_extracts_timezone(self):
        raw = _make_raw(timezone="(GMT-08:00) America/Los_Angeles")
        assert _shape(raw)["timezone"] == "America/Los_Angeles"

    def test_all_required_keys_present(self):
        raw = _make_raw()
        result = _shape(raw)
        for key in ["id", "date", "name", "type", "distance_km", "moving_time_s",
                    "pace_min_per_km", "avg_heartrate", "gear_id", "trainer"]:
            assert key in result

    def test_handles_missing_optional_fields(self):
        raw = {"id": 1, "start_date_local": "2026-01-01T00:00:00Z"}
        result = _shape(raw)
        assert result["distance_km"] == 0
        assert result["avg_heartrate"] is None


def _make_raw(**kwargs):
    defaults = {
        "id": 99,
        "name": "Morning Run",
        "type": "Run",
        "sport_type": "Run",
        "distance": 10000,
        "moving_time": 3000,
        "elapsed_time": 3100,
        "total_elevation_gain": 50,
        "average_speed": 3.3,
        "max_speed": 5.0,
        "average_heartrate": 145,
        "max_heartrate": 165,
        "average_cadence": 88,
        "suffer_score": 30,
        "average_watts": None,
        "gear_id": "g123",
        "kudos_count": 5,
        "workout_type": None,
        "trainer": False,
        "start_latlng": [47.7, -122.1],
        "timezone": "(GMT-08:00) America/Los_Angeles",
        "device_name": "Polar Vantage M3",
        "pr_count": 0,
        "achievement_count": 0,
        "start_date_local": "2026-05-16T07:17:02Z",
    }
    defaults.update(kwargs)
    return defaults
