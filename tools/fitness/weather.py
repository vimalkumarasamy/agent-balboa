import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.open-meteo.com/v1"


def get_weather_forecast(city: str = None, days: int = 3) -> dict:
    """Get weather forecast for the next few days for a given city. Returns daily
    temperature, precipitation, wind speed, and conditions. If no city is provided,
    uses the home city from environment variables."""
    if not city:
        city = os.getenv("HOME_CITY", "Memphis, TN")

    # Geocode city to lat/lon using open-meteo's free geocoding API
    # Strip state/country suffix (e.g. "Everett, WA" → "Everett") for better match
    city_name = city.split(",")[0].strip()
    geo_resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city_name, "count": 1, "language": "en", "format": "json", "countryCode": "US"},
    )
    geo_resp.raise_for_status()
    results = geo_resp.json().get("results")
    if not results:
        return {"error": f"Could not find location: {city}"}

    loc = results[0]
    lat, lon = loc["latitude"], loc["longitude"]

    weather_resp = requests.get(
        f"{API_BASE}/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,weathercode",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_days": days,
            "timezone": "auto",
        },
    )
    weather_resp.raise_for_status()
    data = weather_resp.json()["daily"]

    # WMO weather codes simplified
    def describe(code):
        if code == 0: return "Clear sky"
        if code <= 3: return "Partly cloudy"
        if code <= 48: return "Foggy"
        if code <= 67: return "Rain"
        if code <= 77: return "Snow"
        if code <= 82: return "Rain showers"
        return "Thunderstorm"

    forecast = []
    for i, date in enumerate(data["time"]):
        forecast.append({
            "date": date,
            "condition": describe(data["weathercode"][i]),
            "high_f": data["temperature_2m_max"][i],
            "low_f": data["temperature_2m_min"][i],
            "precipitation_in": data["precipitation_sum"][i],
            "wind_mph": data["windspeed_10m_max"][i],
        })

    return {"location": f"{loc['name']}, {loc.get('admin1', '')}", "forecast": forecast}
