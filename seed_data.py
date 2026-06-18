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
    try:
        with mysql_connection(prompt_password=True) as conn:
            cursor = conn.cursor()
            for table in ["simulation_logs", "rainfall_river_history", "infrastructure", "shelters", "zones", "cities"]:
                cursor.execute(f"DELETE FROM {table}")
            cursor.executemany(
                """
                INSERT INTO cities
                (city_id, name, state, latitude, longitude, map_image_path, map_lat_min, map_lat_max, map_long_min, map_long_max)
                VALUES (%(city_id)s,%(name)s,%(state)s,%(latitude)s,%(longitude)s,%(map_image_path)s,%(map_lat_min)s,%(map_lat_max)s,%(map_long_min)s,%(map_long_max)s)
                """,
                data["cities"],
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

