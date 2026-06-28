from __future__ import annotations

from dataclasses import dataclass
import math

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import MODEL_PATH, MODELS_DIR


@dataclass
class RiskResult:
    score: float
    confidence_low: float
    confidence_high: float
    pattern: str
    discharge_rate: float
    rainfall_warning: str
    explanation: str


def train_and_save_model(history_rows: list[dict]) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(history_rows)
    if df.empty:
        raise ValueError("No history rows supplied for model training")
    rng = np.random.default_rng(7)
    synthetic = []
    for _, row in df.iterrows():
        for _ in range(4): # Increase dataset size slightly
            # Keep rainfall/river closely correlated to the Markov chain history
            rainfall = max(0, float(row["rainfall_mm"]) + rng.normal(0, 5))
            river = max(0.5, float(row["river_level_m"]) + rng.normal(0, 0.15))
            elevation = max(1, rng.normal(24, 22))
            flood_freq = min(0.95, max(0.05, rng.normal(0.42, 0.18)))
            
            # Physics-inspired labeling logic
            # Capacity of the zone to handle water
            drainage_capacity = (elevation / 80.0) + (1.0 - flood_freq) * 0.5 
            
            # Stress placed on the zone by weather and water bodies
            rain_stress = rainfall / 100.0  # Normalized against heavy 100mm event
            river_stress = max(0, (river - 2.0)) / 3.0 # Stress increases sharply as river rises
            
            total_stress = rain_stress + river_stress
            
            # Risk is a non-linear response to stress overwhelming capacity
            risk_ratio = total_stress / (drainage_capacity + 0.1) 
            target = risk_ratio * 30.0
            
            # Elevation penalty: Water pools violently in very low areas
            if elevation < 10:
                target += (10 - elevation) * 3
                
            # Baseline risk bump if history showed a flood
            if bool(row["flood_occurred"]):
                target += 15
                
            synthetic.append(
                {
                    "rainfall_mm": rainfall,
                    "river_level_m": river,
                    "elevation_m": elevation,
                    "historical_flood_frequency": flood_freq,
                    "risk_score": min(100, max(0, target)),
                }
            )
    train_df = pd.DataFrame(synthetic)
    features = train_df[["rainfall_mm", "river_level_m", "elevation_m", "historical_flood_frequency"]]
    target = train_df["risk_score"]
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            ("forest", RandomForestRegressor(n_estimators=150, random_state=12, min_samples_leaf=3)),
        ]
    )
    model.fit(features, target)
    joblib.dump(model, MODEL_PATH)


class FloodRiskModel:
    def __init__(self) -> None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model not found at {MODEL_PATH}; run python train_model.py")
        self.model: Pipeline = joblib.load(MODEL_PATH)

    def score_zone(
        self,
        rainfall_mm: float,
        river_level_m: float,
        zone: dict,
        recent_rainfall: list[float],
        recent_river_levels: list[float],
    ) -> RiskResult:
        features = pd.DataFrame(
            [
                {
                    "rainfall_mm": rainfall_mm,
                    "river_level_m": river_level_m,
                    "elevation_m": zone["elevation_m"],
                    "historical_flood_frequency": zone["historical_flood_frequency"],
                }
            ]
        )
        score = float(np.clip(self.model.predict(features)[0], 0, 100))
        forest = self.model.named_steps["forest"]
        scaled = self.model.named_steps["scale"].transform(features)
        tree_scores = np.array([tree.predict(scaled)[0] for tree in forest.estimators_])
        spread = max(5.0, float(np.std(tree_scores)) * 1.8)
        discharge = _slope(recent_river_levels[-5:]) if recent_river_levels else 0.0
        rain_slope = _slope(recent_rainfall[-5:]) if recent_rainfall else 0.0
        projected = rainfall_mm + rain_slope * 3
        pattern = "Flash-flood pattern" if rainfall_mm >= 60 and rainfall_mm / max(river_level_m, 0.5) > 13 else "Riverine-flood pattern"
        if projected >= rainfall_mm + 12:
            warning = f"Rainfall rising; 3-day projection near {projected:.0f} mm."
        elif projected < rainfall_mm - 8:
            warning = "Rainfall trend easing over the next 1-3 days."
        else:
            warning = "Rainfall trend broadly stable for the next 1-3 days."
        # Determine descriptive terms avoiding developer jargon
        if score > 75:
            risk_desc = "critical"
        elif score > 45:
            risk_desc = "elevated"
        elif score > 20:
            risk_desc = "moderate"
        else:
            risk_desc = "minimal"

        # Rainfall description
        if rainfall_mm > 75:
            rain_desc = "heavy rainfall"
        elif rainfall_mm > 30:
            rain_desc = "moderate rainfall"
        else:
            rain_desc = "low rainfall"

        # River level description
        if river_level_m > 4.5:
            river_desc = "high river levels"
        elif river_level_m > 2.5:
            river_desc = "moderate river levels"
        else:
            river_desc = "low river levels"

        # Elevation description
        if zone["elevation_m"] < 15:
            elev_desc = "low elevation"
        elif zone["elevation_m"] < 45:
            elev_desc = "moderate elevation"
        else:
            elev_desc = "high elevation"

        # Previous flood activity description
        if zone["historical_flood_frequency"] > 0.5:
            freq_desc = "frequent previous flood activity"
        elif zone["historical_flood_frequency"] > 0.2:
            freq_desc = "moderate previous flood activity"
        else:
            freq_desc = "minimal previous flood activity"

        explanation = f"Flood risk is {risk_desc} due to {rain_desc}, {river_desc}, {elev_desc}, and {freq_desc} in this zone."
        return RiskResult(
            score=score,
            confidence_low=max(0, score - spread),
            confidence_high=min(100, score + spread),
            pattern=pattern,
            discharge_rate=discharge,
            rainfall_warning=warning,
            explanation=explanation,
        )


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values))
    y = np.array(values, dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def city_score(zone_results: dict[int, RiskResult]) -> RiskResult:
    values = list(zone_results.values())
    if not values:
        return RiskResult(0, 0, 0, "Riverine-flood pattern", 0, "No trend data.", "No zone data available.")
    score = float(np.mean([r.score for r in values]))
    low = float(np.mean([r.confidence_low for r in values]))
    high = float(np.mean([r.confidence_high for r in values]))
    flash_count = sum(1 for r in values if r.pattern.startswith("Flash"))
    pattern = "Flash-flood pattern" if flash_count >= math.ceil(len(values) / 2) else "Riverine-flood pattern"
    discharge = float(np.mean([r.discharge_rate for r in values]))
    explanation = max(values, key=lambda r: r.score).explanation
    return RiskResult(score, low, high, pattern, discharge, values[0].rainfall_warning, explanation)


 

