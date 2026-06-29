# FloodGuard Backend Complete Reference
*(Generated for Final Exhibition Preparation — Based on the Latest Implementation)*

---

## SECTION 1: Executive Backend Overview

**Backend Philosophy**
FloodGuard is designed as a highly robust, "Offline-First", predictive engine rather than a traditional web application. It favors deterministic mathematical states over transient web calls.

**Layered Architecture**
1. **Presentation Layer (PyQt6)**: Thick client UI (`app.py`), directly managing state and background threads.
2. **Service Layer**: Business logic (`city_service.py`, `risk_service.py`, `weather_service.py`).
3. **Repository Layer**: Data access (`repository.py`, `db.py`) abstracting MySQL queries.

**Data Flow**
UI triggers actions -> Service validates and checks Cache -> If missing, fetches from API -> Stores in DB -> Runs Feature Engineering -> ML Predicts -> UI updates via Thread Signals.

**Control Flow**
Strictly synchronous within services, but executed asynchronously via PyQt `QThread` (`BackgroundWorker`) in the UI to prevent blocking.

**Threading Model**
The `BackgroundWorker` (a subclass of `QRunnable`) executes heavy methods off the main thread. It uses custom PyQt `pyqtSignal` objects (`success`, `failed`, `finished`) to safely update UI components once the heavy lifting is done.

**Persistent Simulation Architecture & Single Source of Truth**
FloodGuard does not generate random weather for a city every time you click on it. The first time a city is searched, the engine seeds 90 days of synthetic historical weather and caches it permanently in the MySQL database. This ensures that the Map, Trends, Dashboard, and Evacuation modules all pull from the exact same mathematical "truth" and remain consistent across reboots.

---

## SECTION 2: Current Folder Structure

```
/FloodGuard/
├── app.py                  # Main Entry Point & UI Presentation Layer
├── setup_db.py             # Database Initializer (Schema)
├── seed_data.py            # Generates the 10 core Indian cities and infrastructure
├── train_model.py          # Machine Learning Training Pipeline
├── test_app.py             # Basic automated smoke test script
├── floodguard/             # Core Backend Package
│   ├── config.py           # Constants, API keys, and UI Palette tokens
│   ├── db.py               # MySQL Connection Pool
│   ├── repository.py       # SQL Queries (Select, Insert)
│   ├── cache_service.py    # Offline caching mechanisms
│   ├── city_service.py     # Geocoding and City retrieval
│   ├── weather_service.py  # Open-Meteo integration & caching
│   ├── weather.py          # Raw HTTP API requests for Meteo/Nominatim
│   ├── risk_service.py     # Orchestrates Unified Simulation and ML Inference
│   ├── risk_model.py       # Scikit-learn Pipeline and Synthetic Data Generation
│   ├── evacuation.py       # NetworkX Routing and Dijkstra
│   ├── map_assets.py       # HTML generators for map popups
│   └── seed_definitions.py # Hardcoded base stats for the 10 cities
├── models/                 # Stores joblib ML artifacts
└── logs/                   # System logging (floodguard.log)
```

---

## SECTION 3: Every Important Backend File

### `floodguard/risk_model.py`
- **Purpose**: Defines the ML architecture, synthetic generation, and inference.
- **Responsibilities**: Generates climate-aware historical weather patterns. Trains the `RandomForestRegressor`. Outputs the `.joblib` model.
- **Inputs**: Real-time sliding window data (rainfall, river level).
- **Outputs**: `RiskResult` (Score, Confidence bounds, Pattern, Explanation).
- **Who calls it**: `risk_service.py` (`UnifiedSimulation`), `train_model.py`.

### `floodguard/evacuation.py`
- **Purpose**: Emergency routing and resource allocation.
- **Responsibilities**: Builds a spherical-distance graph of Zones and Shelters.
- **Inputs**: Current risk scores, population data, shelter locations.
- **Outputs**: List of dictionaries containing priority routes, boat/team counts, and time estimates.
- **Dependencies**: `networkx` for graph math, Haversine formula for distance.

### `floodguard/repository.py`
- **Purpose**: Abstract database interactions.
- **Responsibilities**: Inserts/selects rows. Prevents SQL injection.
- **Inputs**: Pure Python types (strings, floats).
- **Outputs**: Lists of dictionaries representing table rows.
- **Why it exists**: Keeps `app.py` clean from raw SQL strings.

### `floodguard/weather.py`
- **Purpose**: Network I/O.
- **Responsibilities**: Hits Open-Meteo and Nominatim. Implements exponential backoff retries and timeouts (4s/20s).
- **Who calls it**: `weather_service.py`, `city_service.py`.

---

## SECTION 4: Backend Runtime Flow

### Search City Flow
1. User types "Mumbai" and hits Search.
2. `app.py` creates `BackgroundWorker`.
3. Worker calls `city_service.get_city("Mumbai")`.
4. Service checks DB (`repository.py`).
5. If missing, calls `weather.geocode_city()`.
6. Saves to DB, returns city dict.
7. Next, `UnifiedSimulation` is triggered to load or generate the 90-day history.
8. UI updates (Signals emitted).

### ML Prediction Flow
1. User moves slider. `QTimer` waits 250ms (debounce).
2. `update_from_sliders()` fires.
3. `risk_service.score_zone()` is called with new slider values.
4. Reads rolling 7-day history from `UnifiedSimulation`.
5. Feeds into `risk_model.py` (RandomForest).
6. Returns `RiskResult`. Dashboard UI updates immediately. Map updates asynchronously.

---

## SECTION 5: Backend Services

- **`CityService`**: Handles geocoding. Caches results in DB to allow offline searching for previously searched cities.
- **`WeatherService`**: Handles pulling 3-day forecasts. Caches timestamps to prevent spamming Open-Meteo.
- **`RiskService`**: The heaviest service. Ties together the `FloodRiskModel` and `UnifiedSimulation` so the UI gets clean `RiskResult` objects without doing math.
- **`CacheService`**: Logs predictions into `prediction_cache` table for analytical auditing.

---

## SECTION 6: Persistent Simulation Engine

**Why it exists**: Previous versions regenerated random history on every page load, causing the Map and the Dashboard to show different truths. 
**Implementation**: `UnifiedSimulation.get_timeline(city, current_history)`.
**Flow**: 
1. `app.py` loads a city.
2. Checks MySQL `historical_weather` table.
3. If < 90 rows exist, it calls `generate_synthetic_history(city)`.
4. Saves exactly 90 rows to DB.
5. For the rest of the application's lifecycle, the exact same 90 rows are queried. 
**Consistency**: The Dashboard uses this array for "Current Conditions", the ML model uses it for "7-day rolling rain", and the Trends tab plots it directly.

---

## SECTION 7: Machine Learning Backend

- **Current Dataset**: Synthetic, dynamically generated via Auto-Regressive Markov Chains based on city base stats (coastal vs inland).
- **Feature Engineering**: 7 features. Most critical: `7_day_rainfall` (rolling sum) and `river_trend` (gradient difference).
- **Random Forest**: Chosen for tabular speed and stability.
- **Hyperparameters**: Tuned via `RandomizedSearchCV` (`n_estimators`, `max_depth`, `min_samples_split`). 
- **Confidence**: Calculated by pulling the individual predictions of every decision tree in the forest and finding the standard deviation (`np.std`). High standard deviation = Low Confidence.

---

## SECTION 8: Database Backend

- **Current Schema (MySQL)**:
  - `cities` (id, name, lat, lon)
  - `infrastructure` (id, city_id, type, name, lat, lon)
  - `shelters` (id, city_id, name, capacity, lat, lon)
  - `zones` (id, city_id, name, pop, elev, freq, lat, lon)
  - `historical_weather` (id, city_id, date, rain, river, temp)
  - `prediction_cache` (logs predictions for audits)
- **Single Source of Truth**: All tabs read from these tables.
- **Offline Mode**: If the internet fails, all previously searched cities are perfectly usable because their data, maps, and ML models reside entirely in this DB and local `.joblib` files.

---

## SECTION 9: Weather Backend

- **API**: `api.open-meteo.com` (Rainfall/Temp) and `geocoding-api.open-meteo.com`.
- **Retry Logic**: `for attempt in range(3): ... time.sleep(0.5 * (attempt + 1))`.
- **Timeouts**: Strict 4.0 second limit on weather to prevent thread hanging.
- **Failure Recovery**: Triggers UI exceptions that prompt the user to enable Offline Mode.

---

## SECTION 10: Routing Backend

- **NetworkX**: Core library. Constructs an undirected Graph.
- **Dijkstra's Algorithm**: Used to find the shortest path (`nx.shortest_path`) from a vulnerable `Zone` node to a safe `Shelter` node.
- **Weight**: Distance calculated using the spherical Haversine formula (Earth radius 6371km), multiplying lat/lon differences.

---

## SECTION 11: Maps Backend

- **Map Generation**: Python `folium` (a wrapper over JS Leaflet).
- **Polygons (Heatmaps)**: 
  1. `numpy.linspace` creates a 50x50 grid over the city.
  2. The ML model predicts risk for every point in the grid.
  3. `scipy.ndimage.gaussian_filter` smooths the raw grid into natural organic shapes.
  4. `matplotlib.pyplot.contourf` generates vector paths.
  5. The vector paths are parsed and injected into `folium.Polygon`.
- **Threading**: This whole process takes ~400ms, which is why it MUST run in `BackgroundWorker` to prevent freezing the UI.

---

## SECTION 12: Trends Backend

- **Historical Simulation**: Reads the exact same 90-day array generated by `UnifiedSimulation`.
- **Charts**: Embeds `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg` directly into the PyQt window.

---

## SECTION 13: Evacuation Backend

- **Priority**: A mathematical combination of Risk * Population * Proximity.
- **Resource Allocation**:
  - `teams = ceil(population / 500)`
  - `boats = ceil(population / 150)` (only applied if risk > 70).
- **Commander Recommendations**: Hardcoded tactical responses based on risk brackets (e.g., "Deploy NDRF immediately" for >85).

---

## SECTION 14: AI Advisor Backend

- **Ollama Engine**: Uses a local, open-source model (`qwen2.5:3b` or `phi-3:mini`).
- **Endpoint**: Hits `http://localhost:11434/api/chat`.
- **Optimization**: Passes `"keep_alive": -1` in the JSON request. This locks the model in VRAM, eliminating the 5–10 second "cold start" latency during presentations.
- **Context Generation**: Injects RAG-lite context (current rainfall, highest risk zone) invisibly into the `system` message before appending the user's `user` message.

---

## SECTION 15: Algorithms

- **Auto-Regressive Markov Chain**: Uses a transition matrix. If today is "dry", tomorrow has a 90% chance to be "dry" and 10% to be "rainy". This simulates highly realistic weather clusters.
- **Dijkstra**: Standard graph shortest-path algorithm.
- **Gaussian Blur**: `scipy` convolution filter used to blend geospatial risk grids into natural flood contours.

---

## SECTION 16: Threading & Performance

- **QThread & Signals**: PyQt prohibits touching UI elements (like `QLabel.setText`) from outside the main thread.
- **BackgroundWorker**: We pass a Python function to the worker. It runs it on a separate OS thread. When done, it emits a `success(result)` signal back to the main thread, which *then* updates the UI safely.
- **Slider Debounce**: `QTimer` prevents the slider from triggering 100 ML predictions per second while dragging.

---

## SECTION 17: Error Handling

- **Graceful Degradation**: If the API fails, the backend doesn't crash; it raises a caught Exception, which the UI interprets as a cue to disable online features and rely on local cache.

---

## SECTION 18: Backend Data Flow

`User Types "Mumbai"` 
-> `CityService` 
-> `Weather.geocode()` (if not in DB) 
-> `UnifiedSimulation` (pulls 90-day DB timeline) 
-> `RiskService.score_zone()` (calls `RandomForest.predict()`)
-> `BackgroundWorker` emits `success`
-> `app.py` updates Dashboard & Map (`QWebEngineView`).

---

## SECTION 19: Backend Glossary

- **Joblib**: Python library used to serialize (save) the trained ML pipeline to disk (`.joblib`).
- **Haversine**: Mathematical formula to calculate distance between two points on a sphere (Earth).
- **Keep-Alive -1**: A specific Ollama flag that prevents VRAM offloading.

---

## SECTION 20: Backend Viva Questions

1. **Why MySQL instead of SQLite?** MySQL provides better connection pooling for our multi-threaded `BackgroundWorker` accesses.
2. **How do you handle API rate limits?** We cache geocoding forever, and weather timestamps limit Open-Meteo fetches.
3. **What happens if Ollama crashes?** The `requests.post` throws a timeout/connection error, caught gracefully by the UI to display "AI Offline".
4. **Why is folium slow?** Because it builds complex HTML strings. We bypass the UI freeze by generating it in a background thread and injecting it upon completion.
*(More questions inferred from sections above).*

---

## SECTION 21: Code Reading Guide

1. Read **`config.py`** to understand the setup and constants.
2. Read **`db.py` & `repository.py`** to understand the data layout.
3. Read **`risk_model.py`** to understand the brains (ML Pipeline).
4. Read **`app.py`** specifically looking for `run_background` to understand how the backend wires into the UI.

---

## SECTION 22: Backend Cheat Sheet (Rapid Revision)
- **Threads**: `BackgroundWorker` (QRunnable). Use `Signals` to touch UI.
- **ML**: `RandomForestRegressor`, `RandomizedSearchCV`, rolling 7-day features.
- **DB**: MySQL (`cities`, `historical_weather`, `zones`).
- **APIs**: Open-Meteo (Weather), Nominatim (Geocoding), Ollama (AI).
- **Map Limits**: Generating grids > 60x60 causes CPU bottlenecks; optimal is 40x40 to 50x50 with `scipy` blurring.
- **Kiosk Memory**: 2-minute reset timer clears `QWebEngineView` caches to prevent OOM. AI chat capped at 11 items.
