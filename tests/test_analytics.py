import pytest
from unittest.mock import patch
from tools.strava.analytics import (
    _format_time,
    compute_prs_from_races,
    weekly_mileage,
    activity_type_breakdown,
    DISTANCE_RANGES,
)

SAMPLE_ACTIVITIES = [
    {"id": 1, "date": "2026-05-01", "type": "Run", "distance_km": 42.2, "moving_time_s": 10200, "avg_heartrate": 155},
    {"id": 2, "date": "2026-04-15", "type": "Run", "distance_km": 21.1, "moving_time_s": 5100, "avg_heartrate": 148},
    {"id": 3, "date": "2026-04-10", "type": "Run", "distance_km": 10.05, "moving_time_s": 2400, "avg_heartrate": 162},
    {"id": 4, "date": "2026-04-05", "type": "Run", "distance_km": 5.0, "moving_time_s": 1100, "avg_heartrate": 170},
    {"id": 5, "date": "2026-03-20", "type": "Run", "distance_km": 5.1, "moving_time_s": 1200, "avg_heartrate": 168},
    {"id": 6, "date": "2026-03-10", "type": "WeightTraining", "distance_km": 0, "moving_time_s": 3600, "avg_heartrate": 90},
    {"id": 7, "date": "2025-12-01", "type": "Run", "distance_km": 42.5, "moving_time_s": 11000, "avg_heartrate": 158},
]


class TestFormatTime:
    def test_minutes_and_seconds(self):
        assert _format_time(125) == "2:05"

    def test_hours_minutes_seconds(self):
        assert _format_time(3661) == "1:01:01"

    def test_exact_hour(self):
        assert _format_time(3600) == "1:00:00"

    def test_sub_minute(self):
        assert _format_time(45) == "0:45"


class TestComputePrsFromRaces:
    def test_finds_marathon_pr(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = compute_prs_from_races()
        assert "Marathon" in result["personal_records"]
        pr = result["personal_records"]["Marathon"]
        assert pr["time"] == "2:50:00"
        assert pr["date"] == "2026-05-01"

    def test_finds_half_marathon_pr(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = compute_prs_from_races()
        assert "Half Marathon" in result["personal_records"]

    def test_picks_fastest_for_distance(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = compute_prs_from_races()
        # Two 5K runs: 1100s and 1200s — should pick 1100s
        assert result["personal_records"]["5K"]["time"] == "18:20"

    def test_empty_activities(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=[]):
            result = compute_prs_from_races()
        assert result["personal_records"] == {}

    def test_source_is_local(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = compute_prs_from_races()
        assert result["source"] == "local_race_distances"


class TestDistanceRanges:
    def test_all_standard_distances_defined(self):
        for d in ["5K", "10K", "Half Marathon", "Marathon"]:
            assert d in DISTANCE_RANGES

    def test_ranges_dont_overlap(self):
        ranges = list(DISTANCE_RANGES.values())
        for i, (lo1, hi1) in enumerate(ranges):
            for j, (lo2, hi2) in enumerate(ranges):
                if i != j:
                    assert hi1 <= lo2 or hi2 <= lo1, \
                        f"Ranges {list(DISTANCE_RANGES.keys())[i]} and {list(DISTANCE_RANGES.keys())[j]} overlap"


class TestWeeklyMileage:
    def test_returns_correct_number_of_weeks(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = weekly_mileage(weeks=4)
        assert len(result) == 4

    def test_oldest_week_first(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = weekly_mileage(weeks=4)
        assert result[0]["week_of"] < result[-1]["week_of"]

    def test_only_counts_runs(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = weekly_mileage(weeks=52)
        total_km = sum(w["total_km"] for w in result)
        run_km = sum(a["distance_km"] for a in SAMPLE_ACTIVITIES if a["type"] == "Run")
        assert abs(total_km - run_km) < 0.1


class TestActivityTypeBreakdown:
    def test_groups_by_type(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = activity_type_breakdown(days=365)
        assert "Run" in result
        assert "WeightTraining" in result

    def test_run_count_correct(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = activity_type_breakdown(days=365)
        assert result["Run"]["count"] == 6

    def test_sorted_by_count_descending(self):
        with patch("tools.strava.analytics.get_local_activities", return_value=SAMPLE_ACTIVITIES):
            result = activity_type_breakdown(days=365)
        counts = [v["count"] for v in result.values()]
        assert counts == sorted(counts, reverse=True)
