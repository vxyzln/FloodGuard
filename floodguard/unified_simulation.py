from datetime import datetime, timedelta
import math
import random
import json
from pathlib import Path
from floodguard.config import ROOT

class UnifiedSimulation:
    _cache = {}
    _disk_cache_path = ROOT / "assets" / "simulation_state.json"
    _disk_cache_loaded = False

    @classmethod
    def _load_disk_cache(cls):
        if cls._disk_cache_loaded:
            return
        if cls._disk_cache_path.exists():
            try:
                data = json.loads(cls._disk_cache_path.read_text())
                # JSON keys are strings, convert back to int
                cls._cache = {int(k): v for k, v in data.items()}
            except Exception:
                cls._cache = {}
        cls._disk_cache_loaded = True

    @classmethod
    def _save_disk_cache(cls):
        cls._disk_cache_path.parent.mkdir(parents=True, exist_ok=True)
        # JSON keys must be strings
        data = {str(k): v for k, v in cls._cache.items()}
        cls._disk_cache_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def invalidate_cache(cls, city_id: int) -> None:
        """Removes a specific city from the simulation cache, forcing a regeneration on next load."""
        cls._load_disk_cache()
        if city_id in cls._cache:
            del cls._cache[city_id]
            cls._save_disk_cache()

    @classmethod
    def get_timeline(cls, city, db_history, requested_days=1825):
        """
        Generates or retrieves a highly correlated simulation timeline up to requested_days.
        db_history: list of dicts with date, rainfall_mm, river_level_m, flood_occurred
        """
        cls._load_disk_cache()
        
        city_id = city["city_id"]
        city_name = city["name"]
        
        # Check cache
        if city_id in cls._cache:
            # Ensure the cached timeline has the requested length if possible, or just return it
            cached = cls._cache[city_id]
            if len(cached) >= requested_days:
                return cached[-requested_days:]
            return cached
            
        # Dynamic Climate Inference based on Coordinates
        lat = float(city.get("latitude", 20.0))
        lon = float(city.get("longitude", 78.0))
        
        # Heuristic: Coastal cities in India are typically West Coast (lon < 74) or East Coast South (lon > 79, lat < 16) or extreme East (Assam)
        if lon < 74.5 or (lon > 79.5 and lat < 16.5) or lon > 88.0:
            rain_prob_base = 0.35
            rain_intensity = 40.0
            river_base = 2.5
        elif 22.0 < lat < 28.0 and lon < 76.0:
            # Arid / Rajasthan / Gujarat inland
            rain_prob_base = 0.08
            rain_intensity = 15.0
            river_base = 1.0
        elif lat > 26.0:
            # Northern / Moderate
            rain_prob_base = 0.22
            rain_intensity = 25.0
            river_base = 2.0
        else:
            # Central Inland
            rain_prob_base = 0.15
            rain_intensity = 20.0
            river_base = 1.5
            
        c = {"temp_base": 28, "temp_amp": 6, "humidity_base": 65, "wind_base": 14}
        timeline = []
        base_pop = int(city.get("population", 500000))
        
        # We need requested_days. If db_history is shorter, synthesize the older days.
        db_history = sorted(db_history, key=lambda x: x["date"])
        recent_days = len(db_history)
        
        # Build a continuous array of daily parameters for `requested_days`
        daily_params = []
        if recent_days > 0:
            last_date_str = db_history[-1]["date"][:10]
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
        else:
            last_date = datetime.now()
            
        start_date = last_date - timedelta(days=requested_days - 1)
        
        weather_system = 0.0
        current_river = river_base
        soil_sat = 0.0
        
        for i in range(requested_days):
            current_date = start_date + timedelta(days=i)
            # If we are in the synthesized period (before db_history)
            if i < (requested_days - recent_days):
                # Synthesize based on seasonal climate and Auto-Regressive Markov chain
                season_rad = (i % 365) / 365.0 * 2 * math.pi
                seasonality = (1 - math.cos(season_rad)) / 2.0 
                
                drift = random.gauss(0, 0.25)
                # Mean-reverting random walk towards 0.1 to create distinct storm events rather than a 6-month continuous plateau
                weather_system += drift + 0.15 * (0.1 - weather_system)
                
                max_strength = 0.2 + (seasonality * rain_prob_base * 3.5)
                weather_system = max(0.0, min(max_strength, weather_system))
                
                # Higher threshold ensures discrete storms
                if weather_system > 0.4:
                    rain = rain_intensity * (weather_system ** 2.5) * 5.0
                    rain += random.gauss(0, rain * 0.2)
                    rain = max(0.0, min(rain, 350.0))
                    soil_sat = min(1.0, soil_sat + 0.2)
                else:
                    rain = 0.0
                    soil_sat = max(0.0, soil_sat - 0.08)
                    
                discharge = 0.12 * current_river
                runoff_factor = 1.0 + soil_sat * 2.5
                runoff = (rain / 35.0) * runoff_factor
                current_river = max(river_base, current_river - discharge + runoff)
                
                is_flood = bool(rain > 80 or current_river > (river_base * 2.2))
                
                daily_params.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "rainfall_mm": rain,
                    "river_level_m": current_river,
                    "flood_occurred": is_flood
                })
            else:
                # Use actual db_history for the recent tail
                db_idx = i - (requested_days - recent_days)
                daily_params.append(db_history[db_idx])
                
        # Seed consistently so the timeline never jumps on re-render
        random.seed(hash(city_name + "simulation" + str(requested_days)))
        
        points = requested_days
        
        curr_hum = c["humidity_base"]
        curr_wind = c["wind_base"]
        curr_risk = 35.0
        
        for i, row in enumerate(daily_params):
            rain = float(row["rainfall_mm"])
            river = float(row["river_level_m"])
            is_flood = bool(row.get("flood_occurred", False))
            
            # 1. Temperature: Drops heavily when it rains
            phase = (i / points) * 2 * math.pi - math.pi * 0.5
            temp_seasonal = c["temp_base"] + c["temp_amp"] * math.sin(phase)
            temp = temp_seasonal - (rain / 20.0) + random.gauss(0, 0.5)
            
            # 2. Humidity: Spikes when raining, slowly reverts
            target_hum = min(99, c["humidity_base"] + (rain * 2.0))
            curr_hum += 0.3 * (target_hum - curr_hum) + random.gauss(0, 1)
            curr_hum = max(30, min(99, curr_hum))
            
            # 3. Wind: Correlates with heavy rain storms
            target_wind = c["wind_base"] + (rain * 0.8)
            curr_wind += 0.4 * (target_wind - curr_wind) + random.gauss(0, 2)
            curr_wind = max(2, min(80, curr_wind))
            
            # 4. Synthesized Risk Score (smoothed to prevent flatlining at 100)
            rain_stress = rain / 80.0
            river_stress = max(0, (river - 2.5)) / 2.5
            target_risk = min(80.0, (rain_stress + river_stress) * 20.0) + (15 if is_flood else 5)
            
            # Smooth interpolation with natural volatility so it doesn't just peg at 100
            curr_risk += 0.2 * (target_risk - curr_risk) + random.gauss(0, 3.0)
            curr_risk = max(10.0 + random.gauss(0, 2), min(95.0, curr_risk))
            risk_score = curr_risk
            
            # 5. Determine Alert Level
            if risk_score <= 50: alert = "Green"
            elif risk_score <= 70: alert = "Yellow"
            elif risk_score <= 90: alert = "Orange"
            else: alert = "Red"
            
            # 6. Logistics & Exposure (Scales purely with risk)
            pop_low = int(base_pop * 0.05 * (risk_score / 50.0))
            pop_med = int(base_pop * 0.02 * (max(0, risk_score - 40) / 40.0))
            pop_high = int(base_pop * 0.01 * (max(0, risk_score - 70) / 30.0))
            pop_total = pop_low + pop_med + pop_high
            
            timeline.append({
                "date": row["date"][:10],
                "rainfall_mm": round(rain, 1),
                "river_level_m": round(river, 2),
                "temp_c": round(temp, 1),
                "humidity_pct": round(curr_hum, 1),
                "wind_kmh": round(curr_wind, 1),
                "risk_score": round(risk_score, 1),
                "alert_level": alert,
                "flood_occurred": is_flood,
                "pop_low": pop_low,
                "pop_med": pop_med,
                "pop_high": pop_high,
                "pop_total": pop_total,
                "rescue_teams": int(pop_total / 2500),
                "boats_needed": int(pop_total / 800) if risk_score > 75 else 0,
                "ambulances": int(pop_total / 5000),
                "evac_hours": round(1 + (pop_total / 15000.0) + (rain / 50.0), 1)
            })
            
        random.seed()
        cls._cache[city_id] = timeline
        cls._save_disk_cache()
        return timeline

    @classmethod
    def update_present_day(cls, city_id, current_rain, current_river, current_risk):
        """
        Dynamically applies slider "What-If" overrides to the present day in the timeline,
        allowing the entire application (Maps, Trends, Evacuation) to react to user input instantly.
        """
        if city_id not in cls._cache or not cls._cache[city_id]:
            return
            
        timeline = cls._cache[city_id]
        present = timeline[-1]
        
        present["rainfall_mm"] = round(current_rain, 1)
        present["river_level_m"] = round(current_river, 2)
        present["risk_score"] = round(current_risk, 1)
        
        if current_risk <= 50: alert = "Green"
        elif current_risk <= 70: alert = "Yellow"
        elif current_risk <= 90: alert = "Orange"
        else: alert = "Red"
        
        present["alert_level"] = alert
        
        base_pop = 500000 
        present["pop_low"] = int(base_pop * 0.05 * (current_risk / 50.0))
        present["pop_med"] = int(base_pop * 0.02 * (max(0, current_risk - 40) / 40.0))
        present["pop_high"] = int(base_pop * 0.01 * (max(0, current_risk - 70) / 30.0))
        present["pop_total"] = present["pop_low"] + present["pop_med"] + present["pop_high"]
        
        present["rescue_teams"] = int(present["pop_total"] / 2500)
        present["boats_needed"] = int(present["pop_total"] / 800) if current_risk > 75 else 0
        present["ambulances"] = int(present["pop_total"] / 5000)
        present["evac_hours"] = round(1 + (present["pop_total"] / 15000.0) + (current_rain / 50.0), 1)

