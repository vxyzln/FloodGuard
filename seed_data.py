import json

from floodguard.config import CACHE_PATH
from floodguard.db import mysql_connection
from floodguard.map_assets import ensure_placeholder_maps
from floodguard.seed_definitions import build_seed_data


def main() -> None:
    data = build_seed_data()
    ensure_placeholder_maps(data["cities"])
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2))
    # Prepare city records with new columns for database seeding
    db_cities = []
    for city in data["cities"]:
        city_id = city["city_id"]
        # Find elevation as average of its zones
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

    try:
        with mysql_connection(prompt_password=False) as conn:
            cursor = conn.cursor()
            for table in ["simulation_logs", "rainfall_river_history", "infrastructure", "shelters", "zones", "cities"]:
                cursor.execute(f"DELETE FROM {table}")
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
        print("Seeded MySQL database and generated offline cache/maps.")
    except Exception as exc:
        print(f"Generated offline cache/maps. MySQL seed skipped: {exc}")


if __name__ == "__main__":
    main()


 

