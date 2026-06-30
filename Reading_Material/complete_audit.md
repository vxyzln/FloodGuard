# FloodGuard Master Reference Document (Complete Audit)
*(The Definitive Technical Reference for FloodGuard — Current Architecture)*

---

## 1. Executive Overview
**FloodGuard** is an offline-first, professional-grade Emergency Operations Center (EOC) desktop platform. It integrates a Geographic Information System (GIS), a Machine Learning (ML) prediction pipeline, an Evacuation Routing engine, and an offline Artificial Intelligence (AI) conversational advisor. It is designed to assist disaster management authorities (e.g., NDRF, District Collectors) in proactively modeling flood risks, visualizing infrastructural impact, and allocating emergency rescue resources—all without requiring an active internet connection after initial seeding.

---

## 2. Complete Architecture
FloodGuard employs a strict **Service-Repository** architectural pattern built on top of a **Threaded Presentation Layer**.

1. **Presentation Layer (`app.py`)**: A PyQt6 thick client. It strictly acts as a view and controller. No heavy logic executes on the main thread.
2. **Service Layer (`floodguard/*_service.py`)**: Contains all business domain logic, orchestration, and caching strategies.
3. **Repository Layer (`floodguard/repository.py`)**: Handles data persistence, shielding the services from raw SQL.
4. **Data Layer (MySQL)**: The single source of truth for the Persistent Simulation state.

**Offline-First Strategy**: The system seamlessly degrades. If the Open-Meteo or Nominatim APIs fail (or time out), the Services bypass network requests and serve the latest Cached Data directly from the Repository Layer.

---

## 3. Complete Folder Structure
```
/FloodGuard/
├── app.py                  # Main PyQt6 UI and Threading Controller
├── setup_db.py             # Database Initialization & Schema Definition
├── seed_data.py            # Generates synthetic foundational data for 10 cities
├── train_model.py          # Entry point for ML Training and Serialization
├── test_app.py             # Smoke testing suite for application launch
├── models/
│   └── flood_risk_model.joblib # Serialized Scikit-Learn Pipeline
├── logs/
│   └── floodguard.log      # Application runtime logging
└── floodguard/             # Core Backend Module
    ├── __init__.py
    ├── config.py           # Constants, API keys, and UI Palette tokens
    ├── db.py               # MySQL Connection Pool Manager
    ├── repository.py       # SQL Abstraction Layer
    ├── cache_service.py    # Offline prediction caching
    ├── city_service.py     # Geocoding and City metadata management
    ├── weather_service.py  # Open-Meteo orchestration
    ├── weather.py          # Raw HTTP API logic (retries, backoff)
    ├── risk_service.py     # Unified Simulation and ML Orchestration
    ├── risk_model.py       # Random Forest Pipeline & Synthetic Generation
    ├── evacuation.py       # NetworkX Dijkstra Routing
    ├── map_assets.py       # HTML generators for GIS popups
    └── seed_definitions.py # Base geographic heuristics for seeded cities
```

---

## 4. Every Important File

### `app.py`
The largest and most critical file. Responsible for the `QMainWindow`. Initializes the sidebar, the 6 core tabs (Dashboard, Map, Trends, Evacuation, AI, Settings). Handles all user input (sliders, clicks). Uses `BackgroundWorker` (a `QRunnable`) to execute service calls in separate OS threads. Implements `--kiosk` mode event filters for inactivity resets and frameless full-screen rendering.

### `floodguard/risk_model.py`
The brains of the ML. Generates synthetic climate-aware historical arrays using an Auto-Regressive Markov Chain. Trains a `RandomForestRegressor` via `Static Pipeline`. Exposes the `FloodRiskModel` class for live inference during user slider interaction. Calculates confidence intervals by measuring the variance across the random forest's estimators.

### `floodguard/risk_service.py`
The orchestrator. Houses the `UnifiedSimulation` engine. Ensures that a 90-day historical timeline is generated exactly once per city, cached, and served consistently to every tab. Connects slider values to the `FloodRiskModel`.

### `floodguard/evacuation.py`
The graph engine. Converts SQL Zones and Shelters into a `networkx.Graph`. Uses the Haversine formula to compute edge weights (spherical distance). Calculates tactical resource allocations (boats, teams).

### `floodguard/repository.py`
The SQL gateway. Uses parameterized queries to interact with `mysql-connector-python`. Converts SQL tuples back into native Python dictionaries for the Service layer.

### `floodguard/weather.py`
Network I/O. Wraps `requests.get` with a robust 3-attempt exponential backoff loop. Enforces strict timeouts (4.0s for weather, 20.0s for geocoding) to guarantee the thread releases execution quickly during network failures.

---

## 5. Complete Runtime Flow

**Application Startup Flow**
1. User executes `python app.py [--kiosk]`.
2. `FloodGuardWindow.__init__` runs.
3. Services (`CityService`, `WeatherService`, `RiskService`) are instantiated.
4. Database connection pool is initialized.
5. Home tab is displayed.

**Search City Flow**
1. User types city and hits 'Search'.
2. `app.py` spins up `BackgroundWorker`.
3. Calls `CityService.get_city()`.
   - Checks DB `cities` table.
   - If missing, hits Nominatim API. Saves to DB.
4. Calls `UnifiedSimulation.get_timeline()`.
   - Checks DB `historical_weather` table.
   - If missing, generates 90-day Markov synthetic history. Saves to DB.
5. Emits `success` signal. UI updates `current_city`.

**Dashboard & Map Update Flow**
1. User drags a slider (e.g., Rainfall).
2. A 250ms `QTimer` (debounce) prevents spam. Timer expires.
3. `update_from_sliders()` executes.
4. `RiskService.score_zone()` runs ML inference in background.
5. Map generation task begins in background.
6. `numpy` arrays calculated -> `scipy` blurred -> `matplotlib` paths generated -> `folium` injected.
7. HTML string returned. Injected into `QWebEngineView`.

**AI Advisor Flow**
1. User types question.
2. `app.py` constructs a system prompt via RAG (injecting current dashboard stats).
3. Appends user prompt. Limits array to 11 messages (context capping).
4. Submits to local Ollama via `requests.post` with `"keep_alive": -1`.
5. Returns response to chat UI.

---

## 6. Machine Learning Pipeline

- **Dataset**: Synthetically generated. Base parameters (latitude, inland/coastal, topography) influence an Auto-Regressive Markov chain that produces realistic wet/dry monsoon clusters over 90 days.
- **Size**: Seeded for 10 cities * 90 days, augmented dynamically during training to 3,600 highly structured variations (4x multiplier on 900 seed rows).
- **Feature Engineering**: 4 core inputs (Rainfall, River Level, Elevation, Flood Frequency). The most critical are foundational parameters.
- **Model**: `RandomForestRegressor`. Selected for extreme tabular speed, lack of GPU requirement, and resistance to overfitting.
- **Hyperparameters**: Uses a fast static pipeline (n_estimators=150, min_samples_leaf=3) inherited directly from the FV3.1 architecture for instant, reliable training without the overhead of grid search.
- **Persistence**: Saved via `joblib` into `models/flood_risk_model.joblib`. Loaded into memory on app startup.
- **Prediction Pipeline**: Extracts scalar inputs -> formats into Pandas DataFrame -> standardizes (`StandardScaler`) -> infers via RF.
- **Confidence**: `np.std([tree.predict() for tree in forest.estimators_]) * 1.8`. A wide standard deviation across trees implies low confidence in the prediction.
- **Current Limitations**: No hydrodynamic physics (Navier-Stokes). We map statistical probability, not actual water volume dispersion. No absolute Digital Elevation Model (DEM) `.tif` ingestion.
- **Future Improvements**: Transition to Spatio-Temporal Graph Neural Networks (ST-GNNs) for accurate water flow dynamics.

---

## 7. Persistent Simulation (Single Source of Truth)

**Why it exists**: Earlier iterations generated stochastic weather on every page load. The Dashboard showed 100mm rain, but the Map regenerated and showed 20mm. 
**Implementation**: `UnifiedSimulation` in `risk_service.py`.
**Storage**: Saved in the `historical_weather` table in MySQL.
**Behavior**: 
- A city's timeline is generated exactly *once* per database initialization. 
- It represents the Single Source of Truth.
- The Dashboard reads Day 90 for "Current Conditions".
- The ML model reads Days 83-90 for Feature Engineering.
- The Trends tab plots Days 1-90 directly from the DB array.
- This guarantees mathematically identical state correlation across the entire UI.

---

## 8. Database Schema & State

**Engine**: MySQL (`mysql-connector-python`).
**Tables**:
- `cities`: Coordinates and naming.
- `zones`: Topographical regions, population, base elevation, base flood frequency.
- `shelters`: Evacuation points and capacities.
- `infrastructure`: Hospitals, Police, Power stations.
- `historical_weather`: The Persistent Simulation storage.
- `prediction_cache`: Audit logs of generated ML predictions.
**Synchronization**: Read-heavy. Written only on initial city seeding or forced refresh.
**Transactions**: Standard auto-commit for single inserts, manual commit for batch seeding.

---

## 9. Maps & Geographic Visualization

**Rendering Pipeline**:
1. Creates a 40x40 `numpy` grid spanning the city's bounding box.
2. Iterates grid, requesting an ML Risk Score for every `(lat, lon)` coordinate.
3. Applies `scipy.ndimage.gaussian_filter(sigma=2.0)` to organically blur the harsh grid squares into smooth gradients.
4. Generates contour vector paths using `matplotlib.pyplot.contourf`.
5. Iterates paths, converting them to `folium.Polygon` layers.
6. Exports final interactive HTML.
**Optimization**: This operation takes ~400ms. It runs strictly inside a `BackgroundWorker`. The UI remains at 60 FPS while the map generates silently.

---

## 10. Evacuation Routing

**Graph Generation**: `networkx.Graph()`. Nodes are Zones (Origins) and Shelters (Destinations).
**Edge Weights**: Calculated using the spherical Haversine formula.
**Dijkstra's Algorithm**: Calculates the absolute shortest physical path from Danger to Safety.
**Priority Scoring**: `(Risk_Score / 100) * Population * (1 + (10 / max(Distance, 1)))`.
**Resource Math**:
- Rescue Teams = `ceil(Population / 500)`
- Boats = `ceil(Population / 150)` (Applied if Risk > 70).

---

## 11. AI Advisor

**Engine**: Local Ollama instance (`http://localhost:11434/api/chat`).
**Model**: `qwen2.5:3b` or `phi-3:mini`.
**Context Building (RAG-lite)**: 
The system silently constructs a `system` prompt: *"You are FloodGuard... The current city is X, rain is Y, highest risk zone is Z"*.
**Performance Optimization**: 
- We pass `"keep_alive": -1` in the JSON request. This forces Ollama to lock the model into GPU/CPU VRAM forever, eliminating the 5-to-10-second "cold start" load time.
- Context window is artificially hard-capped at 11 array items to prevent token-creep from causing Out-Of-Memory (OOM) application crashes in Kiosk mode.

---

## 12. Threading & Performance

**QThread Architecture**:
We use `QThreadPool.globalInstance()` alongside a custom `BackgroundWorker` subclassing `QRunnable`.
**Signal-Slot Communication**:
PyQt forbids background threads from modifying UI components (like `QLabel.setText`). The `BackgroundWorker` executes the Python logic, then emits a custom `pyqtSignal(object)` (e.g., `success` or `failed`). The Main UI Thread receives this signal and safely updates the widgets.
**UI Freeze Prevention**:
- 250ms `QTimer` slider debounce.
- Asynchronous `folium` string generation.
- Strict 4.0s HTTP socket timeouts on `requests`.
**Exhibition Robustness (Kiosk Mode)**:
- Launched via `python app.py --kiosk`.
- Engages `FramelessWindowHint` and `WindowStaysOnTopHint`.
- Implements a global 2-minute `QEvent` inactivity timer. If the exhibition floor is quiet for 2 minutes, it automatically purges `QWebEngineView` memory caches and resets the dashboard to the home screen to prevent memory fragmentation over an 8-hour exhibition.

---

## 13. Algorithms

- **Random Forest**: An ensemble learning method constructing multiple decision trees at training time and outputting the mean prediction of the individual trees.
- **Auto-Regressive Markov Chain**: A stochastic model describing a sequence of possible events where the probability of each event depends only on the state attained in the previous event (used for generating historically accurate weather).
- **Dijkstra’s Algorithm**: `O(E log V)`. Finds the shortest paths between nodes in a graph.
- **Haversine Formula**: `d = 2r * arcsin(sqrt(sin²((lat₂ - lat₁)/2) + cos(lat₁) * cos(lat₂) * sin²((lon₂ - lon₁)/2)))`.
- **Gaussian Convolution**: Applies a mathematical low-pass filter to 2D arrays to remove high-frequency noise (blocky grids).

---

## 14. Current Strengths

1. **Deterministic Single Source of Truth**: The Persistent Simulation Engine ensures all 6 complex tabs agree on the exact same mathematical state at all times.
2. **Zero-Latency UI**: Extreme adherence to thread isolation guarantees the Qt interface never hangs, regardless of the underlying math load.
3. **Fully Offline Sovereign Capability**: Generates maps, performs ML inference, and chats with LLMs without sending a single byte to the open internet.
4. **Exhibition Hardened**: Automatic memory purging and debounce controls ensure 24/7 unmonitored runtime capability.

---

## 15. Genuine Limitations

1. **Hydrological Abstraction**: Lacks true 3D fluid dynamics. Water volume is statistically inferred based on elevation points rather than simulated via Navier-Stokes physics over a raster DEM.
2. **Street Routing**: NetworkX uses "as-the-crow-flies" spherical Haversine distances rather than true OpenStreetMap road-edge geometries.
3. **Data Source Integration**: Cannot yet ingest live IoT river-level sensors; relies purely on APIs or synthetics.

---

## 16. Future Roadmap

1. **OSM/OSRM Routing Engine**: Replacing Haversine graph edges with true road topology to route *around* flooded intersections.
2. **Spatio-Temporal Graph Neural Networks (ST-GNNs)**: Replacing Random Forest to allow the model to understand the temporal *flow* of water from upstream zones to downstream zones.
3. **Companion App API**: Exporting tactical plans to a lightweight mobile dashboard for deployed NDRF ground teams.

---

## 17. Developer Notes & Maintenance Guidance

- **Map Grid Tuning**: If you need more resolution on the map contours, increase `grid_size = 40` in `redraw_map` inside `app.py`. **WARNING:** Setting this above 70 will exponentially increase background processing time and may cause memory spikes in `scipy`.
- **Modifying the UI**: Never touch a `QWidget` inside a `task()` function submitted to `run_background()`. Always extract the data, return it, and update the UI inside the `success(res)` callback.
- **Database Migrations**: We do not use Alembic. If you change a table schema, you must manually run `DROP TABLE` in MySQL or rewrite `setup_db.py`.
- **Ollama**: Ensure Ollama is running (`ollama serve`) before launching. The `-1` keep alive will lock ~2GB of VRAM/RAM immediately upon the first chat.

---

## 18. Glossary

- **BackgroundWorker**: A custom PyQt class allowing safe off-main-thread execution.
- **DEM**: Digital Elevation Model. True 3D topological data (which we currently approximate).
- **Folium**: A Python wrapper for Leaflet.js used for rendering interactive HTML maps.
- **Haversine**: Mathematical formula for earth-surface distances.
- **Joblib**: Python library used for serializing the Scikit-learn Random Forest model.
- **Ollama**: Offline LLM runner.
- **Persistent Simulation**: Our database methodology ensuring mathematical consistency across UI tabs.
- **QTimer**: PyQt utility used to debounce rapid slider inputs.
- **RAG**: Retrieval-Augmented Generation. Injecting our dashboard data into the LLM prompt.

---

## 19. Revision Summary (Quick Refresh)

**What is it?** An offline-first EOC desktop app.
**How does it work?** 
Search City -> Open-Meteo API -> MySQL Persistent Timeline Seeded -> Feature Engineering (7-day rain) -> Random Forest ML Prediction -> Background Worker -> Matplotlib Contours -> Folium Map -> UI Dashboard.
**What makes it fast?** 250ms debouncers and strict `QThread` offloading.
**What makes it offline?** MySQL cache, `.joblib` ML models, and local Ollama (`qwen2.5:3b`).
**How does it route?** NetworkX Dijkstra graph with Haversine edges.
**How is it Exhibition ready?** `--kiosk` locks the window and engages a 2-minute auto-reset timer to purge browser memory caches and reset state.
**Best feature?** The Unified Persistent Simulation ensures that if the Dashboard says the risk is Critical, the AI, Map, Trends, and Evacuation modules all pull from that exact same dataset simultaneously.
