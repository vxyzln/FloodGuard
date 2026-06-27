from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
MAPS_DIR = ASSETS_DIR / "maps"
MODELS_DIR = ROOT / "models"
CACHE_PATH = ASSETS_DIR / "seed_cache.json"
MODEL_PATH = MODELS_DIR / "flood_risk_model.joblib"

PALETTE = {
    "background": "#F8F6F2",
    "panel": "#FFFFFF",
    "surface": "#F1EFEA",
    "border": "#D6D3D1",
    "text": "#111827",
    "muted": "#6B7280",
    "accent": "#0F766E",
    "accent_hover": "#115E59",
    "green": "#16A34A",
    "yellow": "#CA8A04",
    "orange": "#EA580C",
    "red": "#DC2626",
}


 
