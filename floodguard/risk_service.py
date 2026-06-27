from __future__ import annotations

import math
from .risk_model import FloodRiskModel, RiskResult, city_score

class RiskService:
    def __init__(self) -> None:
        self.model = FloodRiskModel()

    def score_scenario(
        self,
        rainfall: float,
        river_level: float,
        zones: list[dict],
        history: list[dict],
    ) -> dict:
        """
        Runs the ML model predictions on all zones for the given rainfall and river levels,
        and computes the aggregated city risk score.
        """
        if not zones:
            return {
                "zone_results": {},
                "city_result": RiskResult(0.0, 0.0, 0.0, "Riverine-flood pattern", 0.0, "No trend data.", "No zone data available.")
            }
            
        recent_rain = [float(row["rainfall_mm"]) for row in history[-10:]] + [rainfall]
        recent_river = [float(row["river_level_m"]) for row in history[-10:]] + [river_level]
        
        zone_results = {}
        for zone in zones:
            res = self.model.score_zone(
                rainfall,
                river_level,
                zone,
                recent_rain,
                recent_river
            )
            zone_results[int(zone["zone_id"])] = res
            
        city_res = city_score(zone_results)
        
        return {
            "zone_results": zone_results,
            "city_result": city_res
        }

 