from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mysql.connector import Error as MySQLError

from .config import CACHE_PATH
from .db import fetch_all, mysql_connection
from .seed_definitions import alert_level, build_seed_data


class FloodRepository:
    def __init__(self, cache_path: Path = CACHE_PATH) -> None:
        self.cache_path = cache_path
        self.cache = self._load_cache()
        self.using_mysql = self._check_mysql()

    def _load_cache(self) -> dict[str, list[dict]]:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text())
        data = build_seed_data()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(data, indent=2))
        return data

    def _check_mysql(self) -> bool:
        try:
            fetch_all("SELECT 1 AS ok")
            return True
        except Exception:
            return False

    def cities(self) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all("SELECT * FROM cities ORDER BY name")
            except Exception:
                self.using_mysql = False
        return sorted(self.cache["cities"], key=lambda row: row["name"])

    def city_by_name(self, name: str) -> dict | None:
        return next((city for city in self.cities() if city["name"] == name), None)

    def zones(self, city_id: int) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all("SELECT * FROM zones WHERE city_id=%s ORDER BY zone_id", (city_id,))
            except Exception:
                self.using_mysql = False
        return [row for row in self.cache["zones"] if int(row["city_id"]) == int(city_id)]

    def shelters(self, city_id: int) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all("SELECT * FROM shelters WHERE city_id=%s ORDER BY shelter_id", (city_id,))
            except Exception:
                self.using_mysql = False
        return [row for row in self.cache["shelters"] if int(row["city_id"]) == int(city_id)]

    def infrastructure(self, city_id: int) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all("SELECT * FROM infrastructure WHERE city_id=%s ORDER BY infra_id", (city_id,))
            except Exception:
                self.using_mysql = False
        return [row for row in self.cache["infrastructure"] if int(row["city_id"]) == int(city_id)]

    def history(self, city_id: int) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all(
                    "SELECT city_id, date, rainfall_mm, river_level_m, flood_occurred FROM rainfall_river_history WHERE city_id=%s ORDER BY date",
                    (city_id,),
                )
            except Exception:
                self.using_mysql = False
        return [row for row in self.cache["rainfall_river_history"] if int(row["city_id"]) == int(city_id)]

    def simulation_logs(self, city_id: int) -> list[dict]:
        if self.using_mysql:
            try:
                return fetch_all(
                    "SELECT * FROM simulation_logs WHERE city_id=%s ORDER BY timestamp DESC LIMIT 30",
                    (city_id,),
                )
            except Exception:
                self.using_mysql = False
        return self.cache.get("simulation_logs", [])

    def log_simulation(
        self,
        city_id: int,
        rainfall: float,
        river_level: float,
        score: float,
        confidence_low: float,
        confidence_high: float,
        mode: str,
        explanation: str,
    ) -> None:
        level = alert_level(score)
        if self.using_mysql:
            try:
                with mysql_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO simulation_logs
                        (city_id, timestamp, rainfall_input, river_level_input, risk_score, alert_level,
                         confidence_low, confidence_high, mode, explanation_text)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            city_id,
                            datetime.now(),
                            rainfall,
                            river_level,
                            score,
                            level,
                            confidence_low,
                            confidence_high,
                            mode,
                            explanation,
                        ),
                    )
                    conn.commit()
                    cursor.close()
                return
            except MySQLError:
                self.using_mysql = False
        self.cache.setdefault("simulation_logs", []).append(
            {
                "city_id": city_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "rainfall_input": rainfall,
                "river_level_input": river_level,
                "risk_score": score,
                "alert_level": level,
                "confidence_low": confidence_low,
                "confidence_high": confidence_high,
                "mode": mode,
                "explanation_text": explanation,
            }
        )
        self.cache_path.write_text(json.dumps(self.cache, indent=2, default=str))

    def add_city(self, name: str, latitude: float, longitude: float, state: str = "Custom", rainfall_mm: float = 0.0) -> dict[str, Any]:
        existing = self.city_by_name(name)
        if existing:
            return existing
        next_id = self._next_city_id()
        city = {
            "city_id": next_id,
            "name": name,
            "state": state or "Custom",
            "latitude": latitude,
            "longitude": longitude,
            "map_image_path": f"assets/maps/{name.lower().replace(' ', '_')}.png",
            "map_lat_min": latitude - 0.2,
            "map_lat_max": latitude + 0.2,
            "map_long_min": longitude - 0.2,
            "map_long_max": longitude + 0.2,
        }
        self.cache["cities"].append(city)
        for idx in range(1, 4):
            self.cache["zones"].append(
                {
                    "zone_id": next_id * 100 + idx,
                    "city_id": next_id,
                    "name": f"Custom Zone {idx}",
                    "latitude": latitude + (idx - 2) * 0.035,
                    "longitude": longitude - (idx - 2) * 0.035,
                    "elevation_m": 20 + idx * 4,
                    "population": 25000 + idx * 8000,
                    "historical_flood_frequency": 0.25 + idx * 0.08,
                }
            )
            self.cache["shelters"].append(
                {
                    "shelter_id": next_id * 100 + idx,
                    "city_id": next_id,
                    "name": f"Custom Shelter {idx}",
                    "latitude": latitude - (idx - 2) * 0.045,
                    "longitude": longitude + (idx - 2) * 0.045,
                    "capacity": 4000 + idx * 1000,
                    "current_occupancy": 400,
                }
            )
        self.cache.setdefault("infrastructure", []).append(
            {
                "infra_id": next_id * 1000 + 1,
                "city_id": next_id,
                "zone_id": next_id * 100 + 1,
                "type": "hospital",
                "name": f"{name} Relief Hospital",
                "latitude": latitude + 0.02,
                "longitude": longitude - 0.02,
            }
        )
        self.cache.setdefault("rainfall_river_history", []).append(
            {
                "city_id": next_id,
                "date": datetime.now().date().isoformat(),
                "rainfall_mm": round(float(rainfall_mm), 2),
                "river_level_m": 3.0,
                "flood_occurred": bool(float(rainfall_mm) > 70),
            }
        )
        self.cache_path.write_text(json.dumps(self.cache, indent=2))
        if self.using_mysql:
            try:
                self._insert_city_bundle(city)
            except MySQLError:
                self.using_mysql = False
        return city

    def _next_city_id(self) -> int:
        if self.using_mysql:
            try:
                rows = fetch_all("SELECT COALESCE(MAX(city_id), 0) AS max_id FROM cities")
                return int(rows[0]["max_id"]) + 1
            except Exception:
                self.using_mysql = False
        return max(int(city["city_id"]) for city in self.cache["cities"]) + 1

    def _insert_city_bundle(self, city: dict[str, Any]) -> None:
        zones = [row for row in self.cache["zones"] if int(row["city_id"]) == int(city["city_id"])]
        shelters = [row for row in self.cache["shelters"] if int(row["city_id"]) == int(city["city_id"])]
        infrastructure = [row for row in self.cache["infrastructure"] if int(row["city_id"]) == int(city["city_id"])]
        history = [row for row in self.cache["rainfall_river_history"] if int(row["city_id"]) == int(city["city_id"])]
        with mysql_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cities
                (city_id, name, state, latitude, longitude, map_image_path, map_lat_min, map_lat_max, map_long_min, map_long_max)
                VALUES (%(city_id)s,%(name)s,%(state)s,%(latitude)s,%(longitude)s,%(map_image_path)s,%(map_lat_min)s,%(map_lat_max)s,%(map_long_min)s,%(map_long_max)s)
                """,
                city,
            )
            cursor.executemany(
                """
                INSERT INTO zones
                (zone_id, city_id, name, latitude, longitude, elevation_m, population, historical_flood_frequency)
                VALUES (%(zone_id)s,%(city_id)s,%(name)s,%(latitude)s,%(longitude)s,%(elevation_m)s,%(population)s,%(historical_flood_frequency)s)
                """,
                zones,
            )
            cursor.executemany(
                """
                INSERT INTO shelters
                (shelter_id, city_id, name, latitude, longitude, capacity, current_occupancy)
                VALUES (%(shelter_id)s,%(city_id)s,%(name)s,%(latitude)s,%(longitude)s,%(capacity)s,%(current_occupancy)s)
                """,
                shelters,
            )
            cursor.executemany(
                """
                INSERT INTO infrastructure
                (infra_id, city_id, zone_id, type, name, latitude, longitude)
                VALUES (%(infra_id)s,%(city_id)s,%(zone_id)s,%(type)s,%(name)s,%(latitude)s,%(longitude)s)
                """,
                infrastructure,
            )
            cursor.executemany(
                """
                INSERT INTO rainfall_river_history
                (city_id, date, rainfall_mm, river_level_m, flood_occurred)
                VALUES (%(city_id)s,%(date)s,%(rainfall_mm)s,%(river_level_m)s,%(flood_occurred)s)
                """,
                history,
            )
            conn.commit()
            cursor.close()

 
