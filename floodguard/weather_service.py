from __future__ import annotations

import requests

class WeatherService:
    @staticmethod
    def fetch_weather(latitude: float, longitude: float, timeout: float = 5.0) -> dict:
        """
        Fetches current weather (rainfall, temperature, humidity, wind speed) from Open-Meteo API.
        """
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,rain,precipitation",
            "daily": "rain_sum",
            "forecast_days": 3,
        }
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        
        payload = response.json()
        current = payload.get("current", {})
        daily = payload.get("daily", {})
        
        # Open-Meteo rain / precipitation field
        rainfall = float(current.get("rain") or current.get("precipitation") or 0.0)
        temp = float(current.get("temperature_2m") or 0.0)
        humidity = float(current.get("relative_humidity_2m") or 0.0)
        wind_speed = float(current.get("wind_speed_10m") or 0.0)
        daily_rain = daily.get("rain_sum") or []
        
        return {
            "rainfall_mm": rainfall,
            "temperature": temp,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "daily_rainfall": [float(v or 0.0) for v in daily_rain]
        }
