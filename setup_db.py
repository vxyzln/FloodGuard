from floodguard.db import mysql_connection

SCHEMA = [
    "CREATE DATABASE IF NOT EXISTS floodguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    "USE floodguard",
    """
    CREATE TABLE IF NOT EXISTS cities (
        city_id INT PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        state VARCHAR(120) NOT NULL,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        map_image_path VARCHAR(255) NOT NULL,
        map_lat_min DOUBLE NOT NULL,
        map_lat_max DOUBLE NOT NULL,
        map_long_min DOUBLE NOT NULL,
        map_long_max DOUBLE NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS zones (
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
    CREATE TABLE IF NOT EXISTS shelters (
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
    CREATE TABLE IF NOT EXISTS infrastructure (
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
    CREATE TABLE IF NOT EXISTS rainfall_river_history (
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
    CREATE TABLE IF NOT EXISTS simulation_logs (
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
    """,
]


def main() -> None:
    with mysql_connection(prompt_password=True, include_database=False) as conn:
        cursor = conn.cursor()
        for statement in SCHEMA:
            cursor.execute(statement)
        conn.commit()
        cursor.close()
    print("Database floodguard and tables are ready.")


if __name__ == "__main__":
    main()

