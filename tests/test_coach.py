import pytest
from unittest.mock import patch, MagicMock
from tools.fitness.coach import get_coach_plan


SAMPLE_CSV = """\
Monday,Friday,Upper Body,,Week,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday
Activation,Activation,Incline Press,,May-18,Strength,Easy,Hill sprints,Easy,Strength,Easy,Easy
Plank,Pallof Holds,Shoulder Press,,,,,,,,,
Squats,RDL,,,,,,,,,,
"""


def _mock_get(csv_text):
    mock = MagicMock()
    mock.status_code = 200
    mock.text = csv_text
    mock.raise_for_status = lambda: None
    return mock


class TestGetCoachPlan:
    def test_returns_error_when_no_url(self):
        with patch("os.getenv", return_value=""):
            result = get_coach_plan()
        assert "COACH_SHEET_URL" in result

    def test_includes_today_date(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "Today is" in result

    def test_includes_week_schedule(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "WEEK OF May-18" in result
        assert "Monday: Strength" in result
        assert "Wednesday: Hill sprints" in result

    def test_monday_exercises_labeled(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "MONDAY STRENGTH EXERCISES" in result
        assert "- Activation" in result
        assert "- Plank" in result
        assert "- Squats" in result

    def test_friday_exercises_labeled(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "FRIDAY STRENGTH EXERCISES" in result
        assert "- Pallof Holds" in result
        assert "- RDL" in result

    def test_upper_body_exercises(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "UPPER BODY" in result
        assert "- Incline Press" in result

    def test_handles_fetch_error(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", side_effect=Exception("network error")):
            result = get_coach_plan()
        assert "Could not fetch" in result

    def test_no_invented_sets_instruction(self):
        """Output should include the 'do not add sets' instruction to guide the LLM."""
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "do not add sets" in result
