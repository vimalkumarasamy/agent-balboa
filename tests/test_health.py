import pytest
from unittest.mock import patch, MagicMock
from tools.health.base import HealthSnapshot, RecoveryData, SleepData
from tools.health.recovery import get_recovery_status, _fmt_recovery, _fmt_sleep


def _make_recovery(**kwargs):
    defaults = dict(
        date="2026-05-19",
        score=75,
        hrv_rmssd_ms=42.5,
        hrv_score=80,
        breathing_rate_rpm=14.2,
        resting_hr_bpm=52,
        readiness_label="Good",
    )
    defaults.update(kwargs)
    return RecoveryData(**defaults)


def _make_sleep(**kwargs):
    defaults = dict(
        date="2026-05-19",
        duration_minutes=443,
        score=82,
        hrv_avg_ms=41.0,
        hrv_score=78,
        sleep_start="2026-05-18T22:30:00",
        sleep_end="2026-05-19T05:53:00",
        light_sleep_minutes=180,
        deep_sleep_minutes=120,
        rem_sleep_minutes=143,
    )
    defaults.update(kwargs)
    return SleepData(**defaults)


def _make_snapshot(recovery=None, sleep=None):
    return HealthSnapshot(
        date="2026-05-19",
        source="polar",
        recovery=recovery or _make_recovery(),
        sleep=sleep or _make_sleep(),
    )


class TestFormatRecovery:
    def test_includes_readiness_label(self):
        lines = _fmt_recovery(_make_recovery(readiness_label="Good"))
        assert any("Good" in l for l in lines)

    def test_includes_hrv(self):
        lines = _fmt_recovery(_make_recovery(hrv_rmssd_ms=42.5, hrv_score=80))
        assert any("42.5" in l for l in lines)
        assert any("80" in l for l in lines)

    def test_includes_resting_hr(self):
        lines = _fmt_recovery(_make_recovery(resting_hr_bpm=52))
        assert any("52" in l for l in lines)

    def test_handles_missing_optional_fields(self):
        r = _make_recovery(hrv_rmssd_ms=None, hrv_score=None, breathing_rate_rpm=None)
        lines = _fmt_recovery(r)
        assert isinstance(lines, list)


class TestFormatSleep:
    def test_formats_duration(self):
        lines = _fmt_sleep(_make_sleep(duration_minutes=443))
        assert any("7h" in l for l in lines)

    def test_includes_score(self):
        lines = _fmt_sleep(_make_sleep(score=82))
        assert any("82" in l for l in lines)

    def test_includes_sleep_stages(self):
        lines = _fmt_sleep(_make_sleep(deep_sleep_minutes=120, rem_sleep_minutes=143))
        assert any("deep" in l for l in lines)
        assert any("REM" in l for l in lines)

    def test_includes_bedtime(self):
        lines = _fmt_sleep(_make_sleep(
            sleep_start="2026-05-18T22:30:00",
            sleep_end="2026-05-19T05:53:00"
        ))
        assert any("22:30" in l for l in lines)


class TestGetRecoveryStatus:
    def test_returns_message_when_not_configured(self):
        with patch("tools.health.recovery._get_provider", return_value=None):
            result = get_recovery_status()
        assert "No health platform" in result

    def test_returns_recovery_data(self):
        mock_provider = MagicMock()
        mock_provider.get_snapshot.return_value = _make_snapshot()
        with patch("tools.health.recovery._get_provider", return_value=mock_provider):
            result = get_recovery_status()
        assert "Polar" in result
        assert "Good" in result
        assert "42.5" in result

    def test_high_score_recommends_hard_effort(self):
        mock_provider = MagicMock()
        mock_provider.get_snapshot.return_value = _make_snapshot(
            recovery=_make_recovery(score=85)
        )
        with patch("tools.health.recovery._get_provider", return_value=mock_provider):
            result = get_recovery_status()
        assert "Hard" in result or "Well recovered" in result

    def test_low_score_recommends_easy(self):
        mock_provider = MagicMock()
        mock_provider.get_snapshot.return_value = _make_snapshot(
            recovery=_make_recovery(score=25, readiness_label="Compromised")
        )
        with patch("tools.health.recovery._get_provider", return_value=mock_provider):
            result = get_recovery_status()
        assert "easy" in result.lower() or "Low recovery" in result

    def test_handles_provider_error(self):
        mock_provider = MagicMock()
        mock_provider.get_snapshot.side_effect = Exception("API error")
        with patch("tools.health.recovery._get_provider", return_value=mock_provider):
            result = get_recovery_status()
        assert "Could not fetch" in result

    def test_handles_no_data_for_date(self):
        mock_provider = MagicMock()
        mock_provider.get_snapshot.return_value = HealthSnapshot(
            date="2026-05-19", source="polar", recovery=None, sleep=None
        )
        with patch("tools.health.recovery._get_provider", return_value=mock_provider):
            result = get_recovery_status()
        assert "No recovery data" in result
