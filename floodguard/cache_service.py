from __future__ import annotations

import os
import logging
from datetime import datetime, date
from mysql.connector import Error as MySQLError
from .db import mysql_connection, fetch_all, execute
from .seed_definitions import build_seed_data

logger = logging.getLogger("FloodGuard.CacheService")

class CacheService:
    @staticmethod
    def initialize_db_schema_if_needed() -> None:
        """
        Self-healing database setup: checks if tables exist in MySQL;
        if not, creates them and seeds initial data.
        """
        try:
            # Check if the database/tables are already set up
            tables = fetch_all("SHOW TABLES")
            table_names = {list(t.values())[0].lower() for t in tables}
            required_tables = {"cities", "zones", "shelters", "infrastructure", "rainfall_river_history", "simulation_logs"}
            
            if required_tables.issubset(table_names):
                # Database is already initialized
                return
        except Exception:
            # Database might not exist or connection failed. Let's try creating it.
            pass

        try:
            # Step 1: Create DB and select it
            with mysql_connection(prompt_password=False, include_database=False) as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE DATABASE IF NOT EXISTS floodguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cursor.execute("USE floodguard")
                
                # Step 2: Define and create tables
                schema = [
                    "DROP TABLE IF EXISTS simulation_logs",
                    "DROP TABLE IF EXISTS rainfall_river_history",
                    "DROP TABLE IF EXISTS infrastructure",
                    "DROP TABLE IF EXISTS shelters",
                    "DROP TABLE IF EXISTS zones",
                    "DROP TABLE IF EXISTS cities",
                    """
                    CREATE TABLE cities (
                        city_id INT PRIMARY KEY,
                        city VARCHAR(120) NOT NULL UNIQUE,
                        state VARCHAR(120) NOT NULL,
                        latitude DOUBLE NOT NULL,
                        longitude DOUBLE NOT NULL,
                        elevation DOUBLE,
                        temperature DOUBLE,
                        humidity DOUBLE,
                        wind_speed DOUBLE,
                        rainfall DOUBLE,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        map_image_path VARCHAR(255) NOT NULL,
                        map_lat_min DOUBLE NOT NULL,
                        map_lat_max DOUBLE NOT NULL,
                        map_long_min DOUBLE NOT NULL,
                        map_long_max DOUBLE NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE zones (
                        zone_id INT PRIMARY KEY,
                        city_id INT NOT NULL,
                        name VARCHAR(120) NOT NULL,
                        latitude DOUBLE NOT NULL,
                        longitude DOUBLE NOT NULL,
                        elevation_m DOUBLE NOT NULL,
                        population INT NOT NULL,
                        historical_flood_frequency DOUBLE NOT NULL,
                        FOREIGN KEY (city_id) REFERENCES cities(city_id)
                    )
                    """,
                    """
                    CREATE TABLE shelters (
                        shelter_id INT PRIMARY KEY,
                        city_id INT NOT NULL,
                        name VARCHAR(120) NOT NULL,
                        latitude DOUBLE NOT NULL,
                        longitude DOUBLE NOT NULL,
                        capacity INT NOT NULL,
                        current_occupancy INT NOT NULL,
                        FOREIGN KEY (city_id) REFERENCES cities(city_id)
                    )
                    """,
                    """
                    CREATE TABLE infrastructure (
                        infra_id INT PRIMARY KEY,
                        city_id INT NOT NULL,
                        zone_id INT NOT NULL,
                        type ENUM('hospital','school','power_station') NOT NULL,
                        name VARCHAR(160) NOT NULL,
                        latitude DOUBLE NOT NULL,
                        longitude DOUBLE NOT NULL,
                        FOREIGN KEY (city_id) REFERENCES cities(city_id),
                        FOREIGN KEY (zone_id) REFERENCES zones(zone_id)
                    )
                    """,
                    """
                    CREATE TABLE rainfall_river_history (
                        record_id INT AUTO_INCREMENT PRIMARY KEY,
                        city_id INT NOT NULL,
                        date DATE NOT NULL,
                        rainfall_mm DOUBLE NOT NULL,
                        river_level_m DOUBLE NOT NULL,
                        flood_occurred BOOLEAN NOT NULL,
                        FOREIGN KEY (city_id) REFERENCES cities(city_id)
                    )
                    """,
                    """
                    CREATE TABLE simulation_logs (
                        log_id INT AUTO_INCREMENT PRIMARY KEY,
                        city_id INT NOT NULL,
                        timestamp DATETIME NOT NULL,
                        rainfall_input DOUBLE NOT NULL,
                        river_level_input DOUBLE NOT NULL,
                        risk_score DOUBLE NOT NULL,
                        alert_level VARCHAR(20) NOT NULL,
                        confidence_low DOUBLE NOT NULL,
                        confidence_high DOUBLE NOT NULL,
                        mode ENUM('online','offline') NOT NULL,
                        explanation_text TEXT NOT NULL,
                        FOREIGN KEY (city_id) REFERENCES cities(city_id)
                    )
                    """
                ]
                for query in schema:
                    cursor.execute(query)
                conn.commit()
                cursor.close()
            
            # Step 3: Seed initial data
            data = build_seed_data()
            db_cities = []
            for city in data["cities"]:
                city_id = city["city_id"]
                city_zones = [z for z in data["zones"] if z["city_id"] == city_id]
                avg_elevation = sum(z["elevation_m"] for z in city_zones) / len(city_zones) if city_zones else 10.0
                
                db_city = dict(city)
                db_city["city"] = city["name"]
                db_city["elevation"] = round(avg_elevation, 2)
                db_city["temperature"] = 28.5
                db_city["humidity"] = 72.0
                db_city["wind_speed"] = 12.5
                db_city["rainfall"] = 0.0
                db_cities.append(db_city)
                
            with mysql_connection(prompt_password=False) as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT INTO cities
                    (city_id, city, state, latitude, longitude, elevation, temperature, humidity, wind_speed, rainfall, map_image_path, map_lat_min, map_lat_max, map_long_min, map_long_max)
                    VALUES (%(city_id)s,%(city)s,%(state)s,%(latitude)s,%(longitude)s,%(elevation)s,%(temperature)s,%(humidity)s,%(wind_speed)s,%(rainfall)s,%(map_image_path)s,%(map_lat_min)s,%(map_lat_max)s,%(map_long_min)s,%(map_long_max)s)
                    """,
                    db_cities,
                )
                cursor.executemany(
                    """
                    INSERT INTO zones
                    (zone_id, city_id, name, latitude, longitude, elevation_m, population, historical_flood_frequency)
                    VALUES (%(zone_id)s,%(city_id)s,%(name)s,%(latitude)s,%(longitude)s,%(elevation_m)s,%(population)s,%(historical_flood_frequency)s)
                    """,
                    data["zones"],
                )
                cursor.executemany(
                    """
                    INSERT INTO shelters
                    (shelter_id, city_id, name, latitude, longitude, capacity, current_occupancy)
                    VALUES (%(shelter_id)s,%(city_id)s,%(name)s,%(latitude)s,%(longitude)s,%(capacity)s,%(current_occupancy)s)
                    """,
                    data["shelters"],
                )
                cursor.executemany(
                    """
                    INSERT INTO infrastructure
                    (infra_id, city_id, zone_id, type, name, latitude, longitude)
                    VALUES (%(infra_id)s,%(city_id)s,%(zone_id)s,%(type)s,%(name)s,%(latitude)s,%(longitude)s)
                    """,
                    data["infrastructure"],
                )
                cursor.executemany(
                    """
                    INSERT INTO rainfall_river_history
                    (city_id, date, rainfall_mm, river_level_m, flood_occurred)
                    VALUES (%(city_id)s,%(date)s,%(rainfall_mm)s,%(river_level_m)s,%(flood_occurred)s)
                    """,
                    data["rainfall_river_history"],
                )
                conn.commit()
                cursor.close()
                print("Database setup and seeding completed successfully via self-healing DB.")
        except Exception as e:
            print(f"Self-healing database setup failed: {e}")

    @staticmethod
    def check_mysql() -> bool:
        """
        Verifies if connection to MySQL database is active.
        """
        try:
            # Attempt to select a dummy value
            fetch_all("SELECT 1 AS ok")
            return True
        except Exception:
            return False

    @staticmethod
    def city_exists(city_name: str) -> bool:
        """
        Checks if the city exists in MySQL (exact or partial match).
        """
        try:
            rows = fetch_all("SELECT city_id FROM cities WHERE LOWER(city) = LOWER(%s)", (city_name,))
            if rows:
                return True
            # Also check partial
            rows = fetch_all("SELECT city_id FROM cities WHERE LOWER(city) LIKE LOWER(%s)", (f"%{city_name}%",))
            return len(rows) > 0
        except Exception:
            return False

    @staticmethod
    def get_all_cities() -> list[dict]:
        """
        Fetches all cached cities from the database.
        """
        try:
            rows = fetch_all("SELECT * FROM cities ORDER BY city")
            for r in rows:
                r["name"] = r["city"]  # Compatibility alias
            return rows
        except Exception:
            return []

    @staticmethod
    def load_city(city_name: str) -> dict | None:
        """
        Loads all cached data associated with a city.
        """
        try:
            # Find the city record
            rows = fetch_all("SELECT * FROM cities WHERE LOWER(city) = LOWER(%s)", (city_name,))
            if not rows:
                # Try partial match
                rows = fetch_all("SELECT * FROM cities WHERE LOWER(city) LIKE LOWER(%s)", (f"%{city_name}%",))
            if not rows:
                return None
                
            city = rows[0]
            city["name"] = city["city"]  # Compatibility alias
            city_id = int(city["city_id"])
            
            # Fetch relational data
            zones = fetch_all("SELECT * FROM zones WHERE city_id = %s ORDER BY zone_id", (city_id,))
            shelters = fetch_all("SELECT * FROM shelters WHERE city_id = %s ORDER BY shelter_id", (city_id,))
            infrastructure = fetch_all("SELECT * FROM infrastructure WHERE city_id = %s ORDER BY infra_id", (city_id,))
            history = fetch_all(
                "SELECT city_id, date, rainfall_mm, river_level_m, flood_occurred FROM rainfall_river_history WHERE city_id = %s ORDER BY date",
                (city_id,)
            )
            
            # Convert date objects to string for JSON/serializability compatibility if needed
            for h in history:
                if isinstance(h["date"], (datetime, date)):
                    h["date"] = h["date"].isoformat()
                    
            return {
                "city": city,
                "zones": zones,
                "shelters": shelters,
                "infrastructure": infrastructure,
                "history": history
            }
        except Exception as e:
            print(f"Error loading city '{city_name}': {e}")
            return None

    @staticmethod
    def get_next_city_id() -> int:
        """
        Generates the next available unique ID for cities.
        """
        try:
            rows = fetch_all("SELECT COALESCE(MAX(city_id), 0) AS max_id FROM cities")
            return int(rows[0]["max_id"]) + 1
        except Exception:
            return 101  # Start high to avoid collision with seed IDs

    @staticmethod
    def save_city(city_bundle: dict) -> None:
        """
        Saves a newly fetched city and all its associated zones, shelters, infrastructure,
        and simulated historical logs to MySQL.
        """
        city = city_bundle["city"]
        zones = city_bundle["zones"]
        shelters = city_bundle["shelters"]
        infrastructure = city_bundle["infrastructure"]
        history = city_bundle["history"]
        
        with mysql_connection() as conn:
            cursor = conn.cursor()
            try:
                # Insert city record
                cursor.execute(
                    """
                    INSERT INTO cities
                    (city_id, city, state, latitude, longitude, elevation, temperature, humidity, wind_speed, rainfall, map_image_path, map_lat_min, map_lat_max, map_long_min, map_long_max)
                    VALUES (%(city_id)s, %(city)s, %(state)s, %(latitude)s, %(longitude)s, %(elevation)s, %(temperature)s, %(humidity)s, %(wind_speed)s, %(rainfall)s, %(map_image_path)s, %(map_lat_min)s, %(map_lat_max)s, %(map_long_min)s, %(map_long_max)s)
                    """,
                    city
                )
                
                # Insert zones
                cursor.executemany(
                    """
                    INSERT INTO zones
                    (zone_id, city_id, name, latitude, longitude, elevation_m, population, historical_flood_frequency)
                    VALUES (%(zone_id)s, %(city_id)s, %(name)s, %(latitude)s, %(longitude)s, %(elevation_m)s, %(population)s, %(historical_flood_frequency)s)
                    """,
                    zones
                )
                
                # Insert shelters
                cursor.executemany(
                    """
                    INSERT INTO shelters
                    (shelter_id, city_id, name, latitude, longitude, capacity, current_occupancy)
                    VALUES (%(shelter_id)s, %(city_id)s, %(name)s, %(latitude)s, %(longitude)s, %(capacity)s, %(current_occupancy)s)
                    """,
                    shelters
                )
                
                # Insert infrastructure
                cursor.executemany(
                    """
                    INSERT INTO infrastructure
                    (infra_id, city_id, zone_id, type, name, latitude, longitude)
                    VALUES (%(infra_id)s, %(city_id)s, %(zone_id)s, %(type)s, %(name)s, %(latitude)s, %(longitude)s)
                    """,
                    infrastructure
                )
                
                # Insert simulated history
                cursor.executemany(
                    """
                    INSERT INTO rainfall_river_history
                    (city_id, date, rainfall_mm, river_level_m, flood_occurred)
                    VALUES (%(city_id)s, %(date)s, %(rainfall_mm)s, %(river_level_m)s, %(flood_occurred)s)
                    """,
                    history
                )
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    @staticmethod
    def update_city(city_id: int, weather_data: dict) -> None:
        """
        Updates cached weather details (rainfall, temperature, humidity, wind speed)
        and updates the last_updated timestamp in MySQL.
        """
        try:
            execute(
                """
                UPDATE cities
                SET rainfall = %s,
                    temperature = %s,
                    humidity = %s,
                    wind_speed = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE city_id = %s
                """,
                (
                    weather_data.get("rainfall_mm", 0.0),
                    weather_data.get("temperature", 0.0),
                    weather_data.get("humidity", 0.0),
                    weather_data.get("wind_speed", 0.0),
                    city_id
                )
            )
            
            # Also append a new history row for today
            today_str = datetime.now().date().isoformat()
            
            # Check if history for today already exists
            existing = fetch_all(
                "SELECT 1 FROM rainfall_river_history WHERE city_id = %s AND date = %s",
                (city_id, today_str)
            )
            if not existing:
                execute(
                    """
                    INSERT INTO rainfall_river_history (city_id, date, rainfall_mm, river_level_m, flood_occurred)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        city_id,
                        today_str,
                        weather_data.get("rainfall_mm", 0.0),
                        3.0,  # Default river level baseline
                        bool(weather_data.get("rainfall_mm", 0.0) > 70.0)
                    )
                )
        except Exception as e:
            print(f"Failed to update weather in cache: {e}")

    @staticmethod
    def log_simulation(
        city_id: int,
        rainfall: float,
        river_level: float,
        score: float,
        confidence_low: float,
        confidence_high: float,
        mode: str,
        explanation: str,
        alert_level_str: str,
    ) -> None:
        """
        Logs a scenario simulation run to MySQL database.
        """
        try:
            execute(
                """
                INSERT INTO simulation_logs
                (city_id, timestamp, rainfall_input, river_level_input, risk_score, alert_level,
                 confidence_low, confidence_high, mode, explanation_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    city_id,
                    datetime.now(),
                    rainfall,
                    river_level,
                    score,
                    alert_level_str,
                    confidence_low,
                    confidence_high,
                    mode,
                    explanation,
                )
            )
        except Exception as e:
            print(f"Failed to save simulation log: {e}")

    @staticmethod
    def get_simulation_logs(city_id: int) -> list[dict]:
        """
        Retrieves recent simulation logs for the specified city.
        """
        try:
            return fetch_all(
                "SELECT * FROM simulation_logs WHERE city_id = %s ORDER BY timestamp DESC LIMIT 30",
                (city_id,)
            )
        except Exception as e:
            logger.error(f"Database failure: get_simulation_logs failed: {e}")
            return []

    @staticmethod
    def get_all_cached_cities() -> list[dict]:
        """
        Returns all cached cities. Alias for get_all_cities.
        """
        return CacheService.get_all_cities()

    @staticmethod
    def get_stale_cities(hours: float = 6.0) -> list[dict]:
        """
        Returns a list of cities that are stale (older than `hours` hours).
        """
        try:
            cities = CacheService.get_all_cities()
            stale_list = []
            for city in cities:
                lu = city.get("last_updated")
                if not lu:
                    stale_list.append(city)
                    continue
                if isinstance(lu, str):
                    try:
                        lu = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                    except Exception:
                        stale_list.append(city)
                        continue
                lu_naive = lu.replace(tzinfo=None) if lu.tzinfo else lu
                diff = datetime.now() - lu_naive
                if diff.total_seconds() > hours * 3600:
                    stale_list.append(city)
            return stale_list
        except Exception as e:
            logger.error(f"Database failure: get_stale_cities failed: {e}")
            return []

    @staticmethod
    def refresh_city(city_id: int) -> bool:
        """
        Fetches the latest weather data for a city from the API and updates MySQL.
        """
        try:
            # Find the city coordinates
            rows = fetch_all("SELECT latitude, longitude, city FROM cities WHERE city_id = %s", (city_id,))
            if not rows:
                logger.error(f"Refresh failure: City with ID {city_id} not found in database.")
                return False
            city = rows[0]
            lat = float(city["latitude"])
            lon = float(city["longitude"])
            city_name = city["city"]
            
            # Fetch weather online
            from .weather_service import WeatherService
            weather_data = WeatherService.fetch_weather(lat, lon)
            
            # Update city in database
            CacheService.update_city(city_id, weather_data)
            logger.info(f"Cache update: Successfully updated cache for city {city_name} (ID: {city_id})")
            return True
        except Exception as e:
            logger.error(f"Refresh failure: Failed to refresh city ID {city_id}: {e}")
            return False

    @staticmethod
    def refresh_all_cities() -> int:
        """
        Refreshes all stale cities in the database.
        Returns the number of successfully refreshed cities.
        """
        try:
            stale_cities = CacheService.get_stale_cities(hours=6)
            refreshed_count = 0
            for city in stale_cities:
                if CacheService.refresh_city(city["city_id"]):
                    refreshed_count += 1
            return refreshed_count
        except Exception as e:
            logger.error(f"Refresh failure: refresh_all_cities failed: {e}")
            return 0

 