from __future__ import annotations

import requests
import time
import logging

class WeatherTimeoutError(Exception): pass
class WeatherConnectionError(Exception): pass
class WeatherRateLimitError(Exception): pass
class WeatherInvalidResponseError(Exception): pass
class WeatherServiceError(Exception): pass

class WeatherService:
    @staticmethod
    def check_status(timeout: tuple = (3.0, 5.0)) -> dict:
        """
        Lightweight health check for the weather API.
        Returns: {"status": "Connected|Offline|Timeout|API Error", "message": "..."}
        """
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 0,
            "longitude": 0,
            "current": "temperature_2m" # Valid variable to prevent 400 Bad Request
        }
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                return {"status": "API Error", "message": "API Rate Limit Reached"}
            elif response.status_code == 200:
                # Check for valid JSON
                try:
                    payload = response.json()
                    if "current" in payload:
                        return {"status": "Connected", "message": "Weather API available."}
                    else:
                        return {"status": "API Error", "message": "Invalid Response Received (Malformed Data)"}
                except ValueError:
                    return {"status": "API Error", "message": "Invalid Response Received (Not JSON)"}
            else:
                return {"status": "API Error", "message": f"HTTP {response.status_code} Error"}
        except requests.exceptions.Timeout:
            return {"status": "Timeout", "message": "Connection Timed Out"}
        except requests.exceptions.RequestException:
            return {"status": "Offline", "message": "Unable to Reach Weather Server"}

    @staticmethod
    def fetch_weather(latitude: float, longitude: float, timeout: tuple = (3.0, 10.0), progress_callback=None) -> dict:
        """
        Fetches current weather with robust retry logic and timeouts.
        Raises custom exceptions on failure.
        """
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,rain,precipitation",
            "daily": "rain_sum",
            "forecast_days": 3,
        }
        
        max_attempts = 5
        last_exception = None
        
        for attempt in range(max_attempts):
            if progress_callback:
                try:
                    progress_callback(attempt + 1, max_attempts)
                except Exception as e:
                    logging.warning(f"progress_callback failed: {e}")
                    
            start_time = time.time()
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Check for 4xx client errors (don't retry) except 429
                if response.status_code == 429:
                    logging.warning(f"Weather API Rate Limited (Attempt {attempt+1}/{max_attempts}, {response_time_ms}ms)")
                    last_exception = WeatherRateLimitError("API Rate Limit Reached")
                    if attempt < max_attempts - 1:
                        time.sleep(2 ** attempt)
                    continue
                elif 400 <= response.status_code < 500:
                    logging.error(f"Weather API Client Error {response.status_code} (Attempt {attempt+1}/{max_attempts}, {response_time_ms}ms)")
                    raise WeatherInvalidResponseError(f"Invalid Request (HTTP {response.status_code})")
                
                response.raise_for_status()
                
                try:
                    payload = response.json()
                except ValueError:
                    logging.warning(f"Weather API Invalid JSON (Attempt {attempt+1}/{max_attempts}, {response_time_ms}ms)")
                    last_exception = WeatherInvalidResponseError("Invalid Response Received (Not JSON)")
                    if attempt < max_attempts - 1:
                        time.sleep(2 ** attempt)
                    continue
                    
                current = payload.get("current", {})
                daily = payload.get("daily", {})
                
                rainfall = float(current.get("rain") or current.get("precipitation") or 0.0)
                temp = float(current.get("temperature_2m") or 0.0)
                humidity = float(current.get("relative_humidity_2m") or 0.0)
                wind_speed = float(current.get("wind_speed_10m") or 0.0)
                daily_rain = daily.get("rain_sum") or []
                
                logging.info(f"Weather API Success: URL={response.url.split('?')[0]} Status={response.status_code} Time={response_time_ms}ms Attempt={attempt+1}")
                
                return {
                    "rainfall_mm": rainfall,
                    "temperature": temp,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                    "daily_rainfall": [float(v or 0.0) for v in daily_rain]
                }
                
            except requests.exceptions.Timeout as e:
                response_time_ms = int((time.time() - start_time) * 1000)
                logging.warning(f"Weather API Timeout (Attempt {attempt+1}/{max_attempts}, {response_time_ms}ms)")
                last_exception = WeatherTimeoutError("Connection Timed Out")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)
                    
            except requests.exceptions.RequestException as e:
                response_time_ms = int((time.time() - start_time) * 1000)
                logging.warning(f"Weather API Network Error: {e} (Attempt {attempt+1}/{max_attempts}, {response_time_ms}ms)")
                last_exception = WeatherConnectionError("Unable to Reach Weather Server")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)
                    
        logging.error(f"Weather API exhausted retries. Last error: {str(last_exception)}")
        if last_exception:
            raise last_exception
        raise WeatherServiceError("Weather Service Unavailable")
