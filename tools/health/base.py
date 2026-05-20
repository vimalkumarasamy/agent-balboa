"""
Shared data models and abstract interface for health platforms.
Add a new platform by subclassing HealthProvider and implementing get_snapshot().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SleepData:
    date: str
    duration_minutes: int
    score: Optional[int]          # 0-100
    hrv_avg_ms: Optional[float]
    hrv_score: Optional[int]      # 0-100
    sleep_start: Optional[str]
    sleep_end: Optional[str]
    light_sleep_minutes: Optional[int]
    deep_sleep_minutes: Optional[int]
    rem_sleep_minutes: Optional[int]


@dataclass
class RecoveryData:
    date: str
    score: Optional[int]          # normalized 0-100
    hrv_rmssd_ms: Optional[float]
    hrv_score: Optional[int]      # 0-100
    breathing_rate_rpm: Optional[float]
    resting_hr_bpm: Optional[int]
    readiness_label: Optional[str]  # e.g. "Good", "Compromised", "Sustained"


@dataclass
class HealthSnapshot:
    date: str
    source: str                   # "polar", "garmin", "oura", etc.
    recovery: Optional[RecoveryData]
    sleep: Optional[SleepData]


class HealthProvider(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and token are present."""

    @abstractmethod
    def get_snapshot(self, date: Optional[str] = None) -> HealthSnapshot:
        """Return health snapshot for a given date (default: today)."""
