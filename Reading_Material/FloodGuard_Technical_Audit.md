# FloodGuard Technical Audit
*(The Definitive Technical Reference for FloodGuard — Current Architecture)*

---

## 1. Executive Overview

**Project Goals**
FloodGuard aims to eliminate the "wait-and-see" approach of traditional disaster management by providing Emergency Operations Centers (EOCs) with a deterministic, predictive GIS interface. It translates raw meteorological forecasts into high-resolution, street-level infrastructural impact maps using an entirely offline machine learning and routing pipeline.

**Current Architecture**
FloodGuard is structured as a **Service-Repository** pattern wrapped in a **Thick PyQt6 Client**. The UI layer (`app.py`) is decoupled from all blocking operations via `BackgroundWorker` (a subclass of `QRunnable`). The `UnifiedSimulation` engine in `risk_service.py` acts as the master orchestrator, generating a Single Source of Truth timeline that binds the ML, Maps, and AI tightly together.

---

## 2. Current Folder Structure
```
/FloodGuard/
├── app.py                  # PyQt6 UI Controller & Threading Manager
├── setup_db.py             # Schema definition (6 core tables)
├── seed_data.py            # Generates geographic baselines for 10 cities
├── train_model.py          # ML randomized search and joblib serialization
├── test_app.py             # Basic automated smoke test
├── models/
│   └── flood_risk_model.joblib # Serialized Scikit-Learn Model
├── logs/
│   └── floodguard.log      # Application logs
└── floodguard/             # Core Backend Services
    ├── config.py           # Tokens and Paths
    ├── db.py               # MySQL Connection Pool
    ├── repository.py       # SQL Queries (Insert/Select)
    ├── cache_service.py    # Log/Audit saving
    ├── city_service.py     # Geocoding orchestration
    ├── weather_service.py  # Meteo API orchestration
    ├── weather.py          # Raw HTTP with exponential backoff
    ├── risk_service.py     # Unified Simulation logic
    ├── risk_model.py       # ML Random Forest logic
    ├── evacuation.py       # Dijkstra / Haversine NetworkX math
    ├── map_assets.py       # Folium HTML styling generators
    └── seed_definitions.py # Topography heuristic stats
```

---

## 3. Every Important Module

### `app.py`
The master UI file. Heavily relies on `QThreadPool.globalInstance()`. It does not contain mathematical logic; instead, it reads slider inputs, fires `risk_service` calculations via `BackgroundWorker`, and uses custom `pyqtSignal` objects to update `QLabel`s or `QWebEngineView`s upon completion.

### `floodguard/risk_service.py`
Contains the `UnifiedSimulation` engine. Ensures the 90-day history array is generated strictly once per city, cached to MySQL, and served consistently to all modules.

### `floodguard/risk_model.py`
The mathematical engine. Generates synthetic Auto-Regressive Markov Chain climate data. Trains a `RandomForestRegressor`. Calculates model confidence via decision tree variance (`np.std`).

### `floodguard/repository.py`
Abstracts MySQL. Ensures pure Python types (dicts) are returned to Services to keep the architecture clean.

### `floodguard/weather.py`
Handles external HTTP connections with strict 4.0s / 20.0s timeouts and 3-attempt exponential backoff.

---

## 4. Runtime Flow

**Search City Flow**
1. App calls `CityService`.
2. Repository checks DB. If found -> Step 4.
3. If not found -> Hits Nominatim API -> Saves to DB.
4. App calls `UnifiedSimulation`.
5. Repository checks DB. If 90-days exist -> Step 7.
6. If not -> `risk_model` generates Markov 90 days -> Saves to DB.
7. City context loads. Dashboard pulls Day 90.

**Online vs Offline Mode**
In Offline mode, Step 3 and the 3-day Open-Meteo forecast are skipped. The app degrades silently, returning the last known data from MySQL and running purely offline.

**Dashboard Flow**
User moves slider -> 250ms `QTimer` waits (debounce) -> Slider finalized -> `app.py` triggers `BackgroundWorker` -> `score_zone()` runs -> UI Signals emitted -> Text labels update.

**Maps Flow**
Dashboard triggers map -> `BackgroundWorker` computes `numpy` grid -> Applies `scipy.ndimage.gaussian_filter` -> Computes `matplotlib.contourf` -> Exports `folium.Polygon` -> Injects HTML into WebView.

---

## 5. Machine Learning

- **Current Dataset**: Synthetically generated per city. Inland vs coastal base-stats alter the rainfall algorithms.
- **Dataset Size**: ~900 seed rows (10 cities * 90 days), expanded via hyper-variance sampling during `train_model.py` into tens of thousands of rows.
- **Feature Engineering**: 4 core features total. Key features: `7_day_rainfall` (rolling aggregate) and `river_trend` (differential).
- **Random Forest**: Static FV3.1 pipeline. Chosen for extreme CPU inference speed and zero GPU requirement.
- **Confidence Calculation**: Extracted from the variance (`std_dev`) between individual decision trees inside the ensemble.
- **Evaluation**: R² ~0.998, MAE ~0.42.
- **Current Limitations**: Approximated statistical elevations rather than high-res Digital Elevation Model (DEM) ingestion.

---

## 6. Persistent Simulation (Single Source of Truth)

**Why it matters**: A major UI/UX failing in previous versions was randomizing weather on every page load. The Persistent Simulation solves this by generating exactly 90 days of history upon the very first search of a city and committing it to MySQL (`historical_weather` table). 

**Interaction**: 
- **Dashboard**: Displays Day 90 as "Current Conditions".
- **ML**: Reads Days 83-90 to calculate rolling 7-day soil saturation.
- **Trends**: Graphs Days 1-90 sequentially on `matplotlib`.
- **Maps**: Evaluates the grid based entirely on Day 90 + slider adjustments.
This guarantees mathematical harmony across the app.

---

## 7. Database (MySQL)

**Schema**:
- `cities`: Caches geocoded locations.
- `zones`: Base elevation and historical flood frequency stats.
- `shelters`: Evacuation capacity nodes.
- `historical_weather`: The Persistent Simulation timeline (90 rows per city).

**Flow**:
The architecture is read-heavy. Inserts only happen upon the very first search of a new city (caching geocoding and generating the 90-day simulation).

---

## 8. Evacuation

- **Graph Engine**: `networkx.Graph()`.
- **Algorithm**: Dijkstra’s shortest path.
- **Weights**: Spherical Haversine distance between coordinates (earth radius 6371km).
- **Priority Calculation**: `Risk Score * Population * Proximity_Weight`.
- **Resource Allocation**: Teams (`Pop / 500`), Boats (`Pop / 150` if Risk > 70).
- **Commander Recommendations**: Hardcoded tactical responses tied to risk bands (e.g., Critical >85 triggers NDRF deployment).

---

## 9. AI Advisor

- **Engine**: Offline Ollama (`localhost:11434`), model `qwen2.5:3b`.
- **Prompt Generation (RAG-lite)**: The backend invisibly constructs a `system` prompt block containing the current city's name, rainfall, and highest risk zone before the user's message.
- **Performance**: We supply `"keep_alive": -1` inside the POST JSON payload. This permanently pins the LLM into system RAM/VRAM, eliminating the 5-10 second cold-boot latency completely.
- **Memory**: Hard-capped at 11 elements to prevent Kiosk-mode token-creep from overflowing context limits.

---

## 10. Performance & Architecture

- **QThreads & BackgroundWorkers**: Crucial for PyQt. Never block the main loop. `folium` string generation and ML matrix math run asynchronously.
- **Signal-Slot Communication**: Workers emit custom classes back to the main thread (e.g., `self.success.emit(result)`) to update UI elements safely.
- **Slider Debouncing**: A 250ms `QTimer` ensures rapid slider drags don't queue 100 simultaneous ML predictions.
- **Exhibition Robustness (Kiosk Mode)**: `--kiosk` locks the window borderless and runs a 2-minute global inactivity timer. If no user input is detected, it clears the `QWebEngineView` cache (which is prone to memory leaks) and returns to the home screen.

---

## 11. Algorithms (Mathematical Core)

1. **Random Forest Ensemble**: Computes final risk score by averaging the terminal leaves of hundreds of decision trees.
2. **Auto-Regressive Markov Chain**: `P(Wet | Wet) = 0.9` vs `P(Wet | Dry) = 0.1`. Simulates historically accurate weather clumping.
3. **Haversine**: `a = sin²(Δφ/2) + cos φ1 * cos φ2 * sin²(Δλ/2)`. `c = 2 * atan2(√a, √(1−a))`. `d = R * c`.
4. **Gaussian Convolution (SciPy)**: Modifies grid point intensities based on neighboring values to naturally smooth map geometries.

---

## 12. Current Strengths
1. **Unblockable UI**: Deep multi-threading ensures perfect 60 FPS scrolling and interaction regardless of the mathematical payload.
2. **Air-Gapped Sovereign AI**: Can provide advanced operational intelligence in completely disconnected command centers.
3. **Deterministic State**: The Unified Simulation guarantees the math adds up across every chart, map, and sentence generated by the app.

---

## 13. Current Limitations
1. Uses abstract spatial elevations (nodes) instead of true high-resolution raster DEM arrays.
2. Uses straight-line routing (Haversine) instead of true road topology via OpenStreetMap / OSRM.

---

## 14. Future Roadmap
1. Integration of Spatio-Temporal Graph Neural Networks (ST-GNN) for temporal water-flow prediction.
2. Direct OpenStreetMap API ingestion to detect and route *around* flooded road segments.
3. Integration with live IoT river basin sensors to replace synthesized timelines.

---

## 15. Final Technical Summary
FloodGuard is a resilient, offline-first tactical platform designed for Emergency Operations Centers. By leveraging a highly decoupled PyQt6 frontend powered by `QRunnable` threads, it provides a zero-latency interface to a deep Scikit-Learn ML pipeline. The core of its innovation is the Unified Simulation engine, which seeds a Single Source of Truth into a local MySQL database, guaranteeing mathematical harmony between its interactive GIS maps, its NetworkX evacuation graphs, and its RAG-enhanced local Ollama AI Advisor.
