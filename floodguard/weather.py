from __future__ import annotations

import requests


def geocode_city(name: str, timeout: float = 5.0) -> dict:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": name, "count": 1, "language": "en", "format": "json"}
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ValueError("City not found")
    result = results[0]
    return {
        "name": result.get("name", name),
        "state": result.get("admin1") or result.get("country") or "Custom",
        "latitude": float(result["latitude"]),
        "longitude": float(result["longitude"]),
    }


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

