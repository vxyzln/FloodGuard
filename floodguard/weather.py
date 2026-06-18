from __future__ import annotations

import requests


def fetch_open_meteo(latitude: float, longitude: float, timeout: float = 4.0) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "rain,precipitation",
        "daily": "rain_sum",
        "forecast_days": 3,
    }
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current", {})
    daily = payload.get("daily", {})
    rainfall = float(current.get("rain") or current.get("precipitation") or 0)
    daily_rain = daily.get("rain_sum") or []
    return {"rainfall_mm": rainfall, "daily_rainfall": [float(v or 0) for v in daily_rain]}

