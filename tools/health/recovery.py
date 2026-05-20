"""
Unified recovery status tool — works with any configured health platform.
Add new platforms to PROVIDERS in order of preference.
"""
import os
from tools.health.base import HealthSnapshot, RecoveryData, SleepData


def _get_provider():
    if os.getenv("POLAR_CLIENT_ID"):
        from tools.health.polar import PolarProvider
        p = PolarProvider()
        if p.is_configured():
            return p
    # Future: Garmin, Oura, etc.
    return None


def _fmt_recovery(r: RecoveryData) -> list:
    lines = []
    if r.readiness_label:
        lines.append(f"  Readiness: {r.readiness_label}")
    if r.score is not None:
        lines.append(f"  Recovery score: {r.score}/100")
    if r.hrv_rmssd_ms is not None:
        hrv_str = f"{r.hrv_rmssd_ms:.1f}ms"
        if r.hrv_score is not None:
            hrv_str += f" (score {r.hrv_score}/100)"
        lines.append(f"  HRV: {hrv_str}")
    if r.resting_hr_bpm:
        lines.append(f"  Resting HR: {r.resting_hr_bpm} bpm")
    if r.breathing_rate_rpm:
        lines.append(f"  Breathing rate: {r.breathing_rate_rpm:.1f} rpm")
    return lines


def _fmt_sleep(s: SleepData) -> list:
    lines = []
    h, m = divmod(s.duration_minutes, 60)
    dur = f"{h}h {m}min" if h else f"{m}min"
    score_str = f", score {s.score}/100" if s.score is not None else ""
    lines.append(f"  Sleep: {dur}{score_str}")
    if s.sleep_start and s.sleep_end:
        start = s.sleep_start[11:16] if len(s.sleep_start) > 10 else s.sleep_start
        end = s.sleep_end[11:16] if len(s.sleep_end) > 10 else s.sleep_end
        lines.append(f"  Bedtime: {start} → {end}")
    stages = []
    if s.deep_sleep_minutes:
        stages.append(f"deep {s.deep_sleep_minutes}min")
    if s.rem_sleep_minutes:
        stages.append(f"REM {s.rem_sleep_minutes}min")
    if s.light_sleep_minutes:
        stages.append(f"light {s.light_sleep_minutes}min")
    if stages:
        lines.append(f"  Stages: {', '.join(stages)}")
    return lines


def get_recovery_status() -> str:
    """Return today's recovery and sleep data from the configured health platform
    (Polar, Garmin, Oura, etc.). Use this to assess training readiness — a low
    recovery score means favour easy efforts over hard workouts."""
    provider = _get_provider()
    if not provider:
        return "No health platform configured. Add POLAR_CLIENT_ID/SECRET to .env and run scripts/polar_auth.py."

    try:
        snapshot: HealthSnapshot = provider.get_snapshot()
    except Exception as e:
        return f"Could not fetch recovery data from {provider.__class__.__name__}: {e}"

    if not snapshot.recovery and not snapshot.sleep:
        return f"No recovery data available for {snapshot.date} from {snapshot.source}. Device may not have synced yet."

    lines = [f"Recovery status ({snapshot.source.capitalize()}, {snapshot.date}):"]

    if snapshot.recovery:
        lines.extend(_fmt_recovery(snapshot.recovery))
    if snapshot.sleep:
        lines.extend(_fmt_sleep(snapshot.sleep))

    # Training readiness hint for the LLM
    score = snapshot.recovery.score if snapshot.recovery else None
    if score is not None:
        if score >= 70:
            lines.append("\n→ Well recovered. Hard or long efforts appropriate today.")
        elif score >= 40:
            lines.append("\n→ Moderate recovery. Favour moderate intensity — avoid back-to-back hard days.")
        else:
            lines.append("\n→ Low recovery. Recommend easy or rest day. Do not push hard efforts.")

    return "\n".join(lines)
