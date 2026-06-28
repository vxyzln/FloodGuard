from __future__ import annotations

import math
import random
import requests
from datetime import date, timedelta

class CityService:
    @staticmethod
    def geocode_city(name: str, timeout: float = 20.0) -> dict:
        """
        Geocodes a city using Nominatim OpenStreetMap API.
        Returns:
            dict containing city, state, latitude, longitude.
        """
        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "FloodGuard/1.0 (contact@floodguard.example.com)"}
        params = {"q": name, "format": "json", "addressdetails": 1, "limit": 1}
        
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        results = response.json()
        
        if not results:
            raise ValueError(f"City '{name}' not found on OpenStreetMap.")
            
        result = results[0]
        address = result.get("address", {})
        
        # Determine city name
        city_name = address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or name
        # Determine state / country
        state = address.get("state") or address.get("country") or "Custom"
        
        return {
            "city": city_name,
            "state": state,
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
        }

    @staticmethod
    def fetch_elevation(latitude: float, longitude: float, timeout: float = 20.0) -> float:
        """
        Fetches the elevation for a coordinate from the Open-Meteo Elevation API.
        """
        url = "https://api.open-meteo.com/v1/elevation"
        params = {"latitude": latitude, "longitude": longitude}
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        
        elevations = response.json().get("elevation") or []
        if elevations:
            return float(elevations[0])
        return 10.0  # Default fallback elevation in meters

    @classmethod
    def search_and_fetch_city(cls, city_name: str) -> dict:
        """
        Runs geocoding and elevation APIs to fetch city information.
        """
        loc = cls.geocode_city(city_name)
        elev = cls.fetch_elevation(loc["latitude"], loc["longitude"])
        loc["elevation"] = elev
        return loc

    @staticmethod
    def generate_default_city_bundle(city_id: int, city_name: str, state: str, latitude: float, longitude: float, elevation: float, current_rainfall: float) -> dict:
        """
        Generates default zones, shelters, infrastructure, and 90 days of simulated history
        for a newly fetched city to match the visual completeness of seeded cities.
        """
        # Map extents
        lat_min = latitude - 0.2
        lat_max = latitude + 0.2
        lon_min = longitude - 0.2
        lon_max = longitude + 0.2
        
        city_record = {
            "city_id": city_id,
            "city": city_name,
            "state": state,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": elevation,
            "temperature": 28.5,
            "humidity": 72.0,
            "wind_speed": 12.5,
            "rainfall": current_rainfall,
            "map_image_path": f"assets/maps/{city_name.lower().replace(' ', '_')}.png",
            "map_lat_min": lat_min,
            "map_lat_max": lat_max,
            "map_long_min": lon_min,
            "map_long_max": lon_max,
        }
        
        # Generate 3 zones
        zones = []
        zone_names = ["North Basin", "Central Ward", "East Lowlands"]
        for idx, z_name in enumerate(zone_names, start=1):
            angle = (idx / 3) * 2 * math.pi
            zlat = latitude + math.sin(angle) * 0.05
            zlon = longitude + math.cos(angle) * 0.05
            # Elevation fluctuates around the city's base elevation
            zone_elev = max(1.0, elevation + (idx - 2) * 4 + random.randint(-2, 2))
            zones.append({
                "zone_id": city_id * 100 + idx,
                "city_id": city_id,
                "name": z_name,
                "latitude": round(zlat, 5),
                "longitude": round(zlon, 5),
                "elevation_m": float(zone_elev),
                "population": 25000 + idx * 8000 + random.randint(0, 5000),
                "historical_flood_frequency": round(0.15 + idx * 0.08 + random.random() * 0.1, 2)
            })
            
        # Generate 3 shelters
        shelters = []
        shelter_names = ["Civic Relief Centre", "Municipal School Shelter", "Sports Complex Camp"]
        for idx, s_name in enumerate(shelter_names, start=1):
            slat = latitude - (idx - 2) * 0.03
            slon = longitude + (idx - 2) * 0.03
            shelters.append({
                "shelter_id": city_id * 100 + idx,
                "city_id": city_id,
                "name": s_name,
                "latitude": round(slat, 5),
                "longitude": round(slon, 5),
                "capacity": 4000 + idx * 1000,
                "current_occupancy": 400 + idx * 100
            })
            
        # Generate 1 infrastructure facility
        infrastructure = [{
            "infra_id": city_id * 1000 + 1,
            "city_id": city_id,
            "zone_id": zones[0]["zone_id"],
            "type": "hospital",
            "name": f"{city_name} Relief Hospital",
            "latitude": round(latitude + 0.02, 5),
            "longitude": round(longitude - 0.02, 5)
        }]
        
        # Generate 90 days of simulated history
        history = []
        today = date.today()
        # Ensure last day matches the current rainfall
        for days_ago in range(90, 0, -1):
            if days_ago == 1:
                rain = current_rainfall
                river = max(1.5, 2.2 + rain / 50.0)
            else:
                seasonal_wave = 0.5 + 0.5 * math.sin(days_ago / 7)
                rain = max(0.0, random.gauss(20.0 * seasonal_wave, 12))
                river = max(1.5, random.gauss(3.0 + rain / 70.0, 0.5))
                
            flood = rain > 70 or river > 4.6 or (rain > 48 and river > 3.8)
            history.append({
                "city_id": city_id,
                "date": (today - timedelta(days=days_ago)).isoformat(),
                "rainfall_mm": round(rain, 2),
                "river_level_m": round(river, 2),
                "flood_occurred": bool(flood)
            })
            
        return {
            "city": city_record,
            "zones": zones,
            "shelters": shelters,
            "infrastructure": infrastructure,
            "history": history
        }

 

