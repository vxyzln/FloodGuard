from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
MODELS_DIR = ROOT / "models"
CACHE_PATH = ASSETS_DIR / "seed_cache.json"
MODEL_PATH = MODELS_DIR / "flood_risk_model.joblib"

PALETTE = {
    "background": "#0F1B2D",
    "panel": "#16263D",
    "border": "#233247",
    "accent": "#2DD4BF",
    "text": "#E5E7EB",
    "muted": "#94A3B8",
    "green": "#22C55E",
    "yellow": "#FACC15",
    "orange": "#F97316",
    "red": "#EF4444",
}

