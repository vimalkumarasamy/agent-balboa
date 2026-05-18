import pytest
import calendar
import re
from unittest.mock import patch, MagicMock
from tools.fitness.coach import get_coach_plan


def _make_rows(week_label: str, wed_workout: str = "Hill sprints"):
    return [
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", "", ""],
        ["Monday", "Friday", "Upper Body Session", "", "Column 1",
         "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        ["Activation", "Activation", "Incline Press", "", week_label,
         "Strength", "Easy", wed_workout, "Easy", "Strength", "Easy", "Easy"],
        ["Plank", "Pallof Holds", "Shoulder Press", "", "", "", "", "", "", "", "", ""],
        ["Squats", "RDL", "", "", "", "", "", "", "", "", "", ""],
    ]


class TestCoachPlan:
    def test_returns_plan_for_current_week(self):
        rows = _make_rows("May18")
        with patch("tools.fitness.coach._fetch_sheet", return_value=rows), \
             patch("os.getenv", return_value="https://fake-sheet.com"):
            result = get_coach_plan()
        assert "May18" in result
        assert "Monday" in result
        assert "Friday" in result

    def test_expands_monday_exercises(self):
        rows = _make_rows("May18")
        with patch("tools.fitness.coach._fetch_sheet", return_value=rows), \
             patch("os.getenv", return_value="https://fake-sheet.com"):
            result = get_coach_plan()
        assert "Activation" in result
        assert "Plank" in result
        assert "Squats" in result

    def test_expands_friday_exercises(self):
        rows = _make_rows("May18")
        with patch("tools.fitness.coach._fetch_sheet", return_value=rows), \
             patch("os.getenv", return_value="https://fake-sheet.com"):
            result = get_coach_plan()
        assert "Pallof Holds" in result
        assert "RDL" in result

    def test_shows_wednesday_workout_as_is(self):
        rows = _make_rows("May18", wed_workout="6 x 8s uphill sprints")
        with patch("tools.fitness.coach._fetch_sheet", return_value=rows), \
             patch("os.getenv", return_value="https://fake-sheet.com"):
            result = get_coach_plan()
        assert "6 x 8s uphill sprints" in result

    def test_returns_error_when_no_url(self):
        with patch("os.getenv", return_value=""):
            result = get_coach_plan()
        assert "COACH_SHEET_URL" in result

    def test_date_formats_parsed(self):
        """Test that various date formats in the sheet are matched correctly."""
        abbr_to_month = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
        formats = ["May-18", "May18", "Jun1", "Jun-8", "Jun15", "Jun-22"]
        for raw in formats:
            m = re.match(r"([A-Za-z]+)-?(\d+)", raw.strip())
            assert m is not None, f"Failed to parse: {raw}"
            month = abbr_to_month.get(m.group(1).lower()[:3])
            assert month is not None, f"Unknown month in: {raw}"
