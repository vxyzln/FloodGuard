from __future__ import annotations

from datetime import date, timedelta
import math
import random

CITY_SPECS = [
    ("Mumbai", "Maharashtra", 19.0760, 72.8777, 18.86, 19.30, 72.70, 73.05),
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707, 12.85, 13.25, 80.05, 80.35),
    ("Kolkata", "West Bengal", 22.5726, 88.3639, 22.35, 22.75, 88.15, 88.55),
    ("Patna", "Bihar", 25.5941, 85.1376, 25.40, 25.75, 84.95, 85.35),
    ("Guwahati", "Assam", 26.1445, 91.7362, 25.95, 26.32, 91.50, 91.95),
    ("Surat", "Gujarat", 21.1702, 72.8311, 20.98, 21.35, 72.65, 73.02),
    ("Kochi", "Kerala", 9.9312, 76.2673, 9.78, 10.08, 76.12, 76.42),
    ("Bengaluru", "Karnataka", 12.9716, 77.5946, 12.78, 13.15, 77.38, 77.82),
    ("Hyderabad", "Telangana", 17.3850, 78.4867, 17.18, 17.58, 78.25, 78.72),
    ("Varanasi", "Uttar Pradesh", 25.3176, 82.9739, 25.15, 25.48, 82.78, 83.16),
]

ZONE_NAMES = ["North Basin", "Central Market", "River Ward", "Old Town", "East Lowlands", "South Junction"]
SHELTER_NAMES = ["Civic Relief Centre", "Municipal School Shelter", "Sports Complex Camp"]
INFRA_TYPES = ["hospital", "school", "power_station"]


def alert_level(score: float) -> str:
    if score <= 25:
        return "Green"
    if score <= 50:
        return "Yellow"
    if score <= 75:
        return "Orange"
    return "Red"


def build_seed_data() -> dict:
    random.seed(42)
    result: dict[str, list[dict]] = {
        "cities": [],
        "zones": [],
        "shelters": [],
        "infrastructure": [],
        "rainfall_river_history": [],
    }
    today = date.today()
    for city_id, spec in enumerate(CITY_SPECS, start=1):
        name, state, lat, lon, lat_min, lat_max, lon_min, lon_max = spec
        result["cities"].append(
            {
                "city_id": city_id,
                "name": name,
                "state": state,
                "latitude": lat,
                "longitude": lon,
                "map_image_path": f"assets/maps/{name.lower().replace(' ', '_')}.png",
                "map_lat_min": lat_min,
                "map_lat_max": lat_max,
                "map_long_min": lon_min,
                "map_long_max": lon_max,
            }
        )

        for index, zone_name in enumerate(ZONE_NAMES, start=1):
            angle = (index / len(ZONE_NAMES)) * 2 * math.pi
            zlat = lat + math.sin(angle) * (lat_max - lat_min) * 0.25
            zlon = lon + math.cos(angle) * (lon_max - lon_min) * 0.25
            elevation = max(2, 38 - index * 4 + random.randint(-3, 8))
            if name in {"Mumbai", "Chennai", "Kochi", "Kolkata", "Surat"}:
                elevation = max(1, elevation - 16)
            if name in {"Bengaluru", "Hyderabad"}:
                elevation += 410
            result["zones"].append(
                {
                    "zone_id": city_id * 100 + index,
                    "city_id": city_id,
                    "name": zone_name,
                    "latitude": round(zlat, 5),
                    "longitude": round(zlon, 5),
                    "elevation_m": float(elevation),
                    "population": 35000 + index * 9000 + random.randint(0, 11000),
                    "historical_flood_frequency": round(0.18 + index * 0.07 + random.random() * 0.16, 2),
                }
            )

        for index, shelter_name in enumerate(SHELTER_NAMES, start=1):
            result["shelters"].append(
                {
                    "shelter_id": city_id * 100 + index,
                    "city_id": city_id,
                    "name": shelter_name,
                    "latitude": round(lat + (index - 2) * (lat_max - lat_min) * 0.12, 5),
                    "longitude": round(lon - (index - 2) * (lon_max - lon_min) * 0.12, 5),
                    "capacity": 4500 + index * 1800,
                    "current_occupancy": 700 + index * 500,
                }
            )

        for zone in [z for z in result["zones"] if z["city_id"] == city_id][:3]:
            result["infrastructure"].append(
                {
                    "infra_id": city_id * 1000 + len(result["infrastructure"]) + 1,
                    "city_id": city_id,
                    "zone_id": zone["zone_id"],
                    "type": INFRA_TYPES[(zone["zone_id"] + city_id) % len(INFRA_TYPES)],
                    "name": f"{name} {zone['name']} Facility",
                    "latitude": zone["latitude"] + 0.01,
                    "longitude": zone["longitude"] - 0.01,
                }
            )

        city_rain_bias = 35 if name in {"Mumbai", "Kochi", "Guwahati"} else 22
        for days_ago in range(90, 0, -1):
            seasonal_wave = 0.5 + 0.5 * math.sin(days_ago / 7)
            rainfall = max(0, random.gauss(city_rain_bias * seasonal_wave, 18))
            river = max(1.5, random.gauss(3.2 + rainfall / 70, 0.55))
            flood = rainfall > 70 or river > 4.6 or (rainfall > 48 and river > 3.8)
            result["rainfall_river_history"].append(
                {
                    "city_id": city_id,
                    "date": (today - timedelta(days=days_ago)).isoformat(),
                    "rainfall_mm": round(rainfall, 2),
                    "river_level_m": round(river, 2),
                    "flood_occurred": bool(flood),
                }
            )
    return result

