from __future__ import annotations

import requests
import time
import logging

class WeatherService:
    @staticmethod
    def fetch_weather(latitude: float, longitude: float, timeout: float = 20.0) -> dict:
        """
        Fetches current weather (rainfall, temperature, humidity, wind speed) from Open-Meteo API.
        Includes 3 retries with exponential backoff. Returns fallback if totally unavailable.
        """
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,rain,precipitation",
            "daily": "rain_sum",
            "forecast_days": 3,
        }
        
        for attempt in range(3):
            try:
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
            except requests.exceptions.RequestException as e:
                logging.warning(f"Weather API attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 1s, 2s
        
        logging.error("Weather API temporarily unavailable. Using fallback zeros.")
        return {
            "rainfall_mm": 0.0,
            "temperature": 0.0,
            "humidity": 0.0,
            "wind_speed": 0.0,
            "daily_rainfall": [],
            "api_error": True
        }

 