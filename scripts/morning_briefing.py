"""
Generate and send the daily morning briefing to Telegram.
Runs via launchd — install with: bash scripts/install_schedule.sh

Output example:
    🌅 Good morning — Tuesday May 20

    💪 Recovery: Good · HRV 42ms · Sleep 7h 23min
    🏃 Today (Tuesday): Easy run
    🌤 Weather: 62°F, Partly cloudy, wind 8mph
    📈 This week: 18km across 3 runs

    Ask me anything — reply in the Balboa terminal.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from datetime import date
from tools.health.recovery import get_recovery_status
from tools.fitness.coach import get_coach_plan
from tools.fitness.weather import get_weather_forecast
from tools.strava.sync import get_local_activities
from tools.notifications.telegram import send_message


def _recovery_line() -> str:
    raw = get_recovery_status()
    if "No health platform" in raw or "No recovery data" in raw:
        return "No recovery data yet — sync your watch."
    parts = []
    for line in raw.split("\n"):
        line = line.strip()
        if "Readiness:" in line:
            parts.append(line.replace("Readiness:", "").strip())
        elif "HRV:" in line and "ms" in line:
            # Extract just "42.5ms"
            for word in line.split():
                if "ms" in word:
                    parts.append(f"HRV {word.strip(',')}")
                    break
        elif "Sleep:" in line and "min" in line:
            # Extract "7h 23min, score 82/100"
            val = line.replace("Sleep:", "").strip()
            parts.append(f"Sleep {val}")
    return " · ".join(parts) if parts else raw.split("\n")[0]


def _today_workout_line(today_name: str) -> str:
    plan = get_coach_plan()
    for line in plan.split("\n"):
        if line.strip().startswith(today_name + ":"):
            workout = line.split(":", 1)[-1].strip()
            return workout or "Rest"
    return "Check coach plan"


def _weather_line() -> str:
    result = get_weather_forecast()
    if "error" in result:
        return "Weather unavailable"
    forecast = result.get("forecast", [])
    if not forecast:
        return "No forecast"
    today = forecast[0]
    return (
        f"{today['high_f']:.0f}°F / {today['low_f']:.0f}°F, "
        f"{today['condition']}, wind {today['wind_mph']:.0f}mph"
    )


def _weekly_load_line() -> str:
    acts = get_local_activities(days=7, activity_type="Run")
    if not acts:
        return "No runs this week yet"
    total_km = sum(a.get("distance_km", 0) for a in acts)
    return f"{total_km:.1f}km across {len(acts)} run{'s' if len(acts) != 1 else ''} this week"


def generate_briefing() -> str:
    today = date.today()
    day_name = today.strftime("%A")
    date_str = today.strftime("%B %d")

    recovery = _recovery_line()
    workout = _today_workout_line(day_name)
    weather = _weather_line()
    load = _weekly_load_line()

    return (
        f"🌅 <b>Good morning — {day_name} {date_str}</b>\n"
        f"\n"
        f"💪 <b>Recovery:</b> {recovery}\n"
        f"🏃 <b>Today ({day_name}):</b> {workout}\n"
        f"🌤 <b>Weather:</b> {weather}\n"
        f"📈 <b>Load:</b> {load}\n"
        f"\n"
        f"Ask me anything — type <code>balboa</code> in your terminal."
    )


if __name__ == "__main__":
    print("Generating briefing...")
    briefing = generate_briefing()
    print(briefing)
    print("\nSending to Telegram...")
    send_message(briefing)
    print("Done.")
