import pytest
from unittest.mock import patch, MagicMock
from tools.fitness.coach import get_coach_plan, _csv_to_table


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

    def test_includes_sheet_content(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "May-18" in result
        assert "Strength" in result
        assert "Hill sprints" in result

    def test_includes_exercises(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", return_value=_mock_get(SAMPLE_CSV)):
            result = get_coach_plan()
        assert "Activation" in result
        assert "Plank" in result
        assert "Squats" in result

    def test_handles_fetch_error(self):
        with patch("os.getenv", return_value="https://docs.google.com/spreadsheets/d/abc/edit?gid=0"), \
             patch("requests.get", side_effect=Exception("network error")):
            result = get_coach_plan()
        assert "Could not fetch" in result


class TestCsvToTable:
    def test_filters_empty_rows(self):
        csv_text = "a,b\n\n\nc,d\n"
        result = _csv_to_table(csv_text)
        assert result.count("\n") == 1  # two data rows, one newline

    def test_pipe_delimited(self):
        result = _csv_to_table("a,b,c\n")
        assert "|" in result

    def test_empty_sheet(self):
        result = _csv_to_table("\n\n")
        assert "empty" in result
