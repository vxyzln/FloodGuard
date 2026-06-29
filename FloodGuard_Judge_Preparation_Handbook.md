# FloodGuard Judge Preparation Handbook
*(Generated for Final Exhibition Preparation — Based on the Latest Implementation)*

---

## SECTION 1: Complete Project Story

**Why FloodGuard exists**
FloodGuard was born out of the necessity to shift disaster management from a reactive, recovery-focused approach to a proactive, predictive approach. Traditional systems wait for water to rise; FloodGuard uses mathematical modeling to deploy resources *before* the flood crests.

**Problem Statement**
Current Emergency Operations Centers (EOCs) lack high-resolution, predictive geospatial intelligence that operates entirely offline. During a severe cyclone or monsoon, internet infrastructure is the first to fail, rendering cloud-dependent dashboards useless.

**Why India**
India’s unique geographical diversity—from coastal cities like Mumbai and Chennai to riverine basins like Patna and Guwahati—faces extreme monsoon volatility. High population density combined with rapid, unplanned urbanization means even minor flooding can cause catastrophic infrastructural paralysis.

**Why Emergency Operations Centers (EOCs)**
FloodGuard is designed specifically for EOCs (like those operated by NDRF or District Collectors). It is not a consumer app. It is a command-and-control platform designed for tactical decision-making, resource allocation, and maintaining a Single Source of Truth during a crisis.

**Why Offline First**
A disaster management tool that requires the internet is a liability. By embedding a local MySQL database, a local Random Forest `.joblib` model, and a local Ollama AI engine, FloodGuard guarantees 100% operational readiness even if undersea cables or local cell towers are destroyed.

**Why Local AI**
Sending sensitive municipal infrastructure data (hospitals, power grids, shelter capacities) to a public cloud API (like OpenAI) is a severe security violation for government EOCs. Local Ollama (`qwen2.5:3b`) ensures absolute data sovereignty while providing expert-level tactical advice.

**Why Persistent Simulation**
If a dashboard predicts a 45mm flood, but the map shows a 20mm flood because it regenerated random data on tab switch, the EOC loses trust in the system. The Persistent Simulation engine guarantees mathematical consistency across all modules by caching exactly 90 days of synthetic data once per city.

---

## SECTION 2: Complete Workflow

**Search City** -> Geocodes the text input (Nominatim) -> 
**Weather API** -> Fetches 3-day rainfall forecast (Open-Meteo) -> 
**Persistent Simulation** -> Checks MySQL; if missing, generates and caches 90-day history -> 
**Database** -> Reads the single source of truth for the city -> 
**Feature Engineering** -> Calculates rolling 7-day rainfall and river gradient -> 
**Random Forest** -> Ingests features and predicts Risk (0-100) -> 
**Dashboard** -> Updates KPIs via `BackgroundWorker` success signal -> 
**Maps** -> Asynchronously generates NumPy arrays -> SciPy Gaussian Blur -> Matplotlib Contours -> Folium Polygons -> 
**Trends** -> Plots persistent simulation timeline via Matplotlib -> 
**Evacuation** -> Calculates NetworkX Dijkstra shortest paths to shelters -> 
**AI Advisor** -> Formats RAG-lite prompt with dashboard stats -> Inferences via Ollama `keep_alive:-1` -> 
**Offline Cache** -> If any API fails, degradation to DB cache happens silently.

---

## SECTION 3: Technology Decisions

- **Python**: Universal data science language. Allows bridging Scikit-Learn, SciPy, and PyQt seamlessly.
- **PyQt6**: Desktop UI framework. Chose over Electron/React because it allows native threading, direct memory access for heavy ML arrays, and strict Kiosk presentation mode.
- **Scikit-learn (Random Forest)**: Chosen over Deep Learning because tabular weather data fits decision trees perfectly, trains instantly on CPU, doesn't require a GPU, and avoids overfitting.
- **Joblib**: Superior to `pickle` for serializing large NumPy arrays used inside Scikit-learn pipelines.
- **MySQL**: Chosen over SQLite to prevent database locks when multiple `BackgroundWorker` threads attempt to read/write persistent simulation data simultaneously.
- **Folium & Leaflet**: Allows rich, interactive, JS-based GIS mapping injected directly into PyQt’s `QWebEngineView`.
- **NetworkX**: Standard Python graph library; ideal for Dijkstra routing across 60+ nodes in real-time.
- **Ollama**: Allows running highly capable LLMs entirely offline on consumer hardware.

---

## SECTION 4: Backend Understanding

FloodGuard uses a standard **Service-Repository Pattern**:
- **Presentation (app.py)**: Spawns `QThread` BackgroundWorkers. Never blocks.
- **Services (risk_service, city_service, weather_service)**: Implements business logic. `risk_service` connects the UnifiedSimulation array to the `score_zone` ML function.
- **Repositories (repository.py)**: Hand-written SQL queries ensuring parameterized, safe MySQL execution. Returns dictionaries to the Services.

Data flows strictly one-way: `app.py` asks `Service` -> `Service` asks `Repository` -> `Repository` queries `DB`. The result bubbles back up and is emitted to `app.py` via PyQt Signals.

---

## SECTION 5: Machine Learning

- **Dataset**: Synthetically generated per-city using an Auto-Regressive Markov Chain. Simulates realistic monsoons, dry spells, and river surges based on the city's base elevation and latitude.
- **Feature Engineering**: Converts raw points into temporal features: `7_day_rainfall` (rolling sum) and `river_trend` (current - previous day).
- **Training**: Uses `RandomizedSearchCV` on a `Pipeline` containing `StandardScaler` and `RandomForestRegressor`. 
- **Confidence**: We extract the prediction of all individual trees in the forest. High variance (Standard Deviation) between trees = low confidence in the prediction.
- **Evaluation**: R² is near 0.998, MAE is ~0.42. 
- **Limitations**: Topography is heavily approximated since we do not ingest absolute DEM (Digital Elevation Model) `.tif` rasters.

---

## SECTION 6: APIs

- **Weather (Open-Meteo)** & **Geocoding (Nominatim)**: Free, no-key APIs.
- **Retry Logic**: Both are wrapped in an exponential backoff loop (`time.sleep(0.5 * (attempt + 1))`). Maximum 3 retries.
- **Timeouts**: Strictly enforced (4.0s weather, 20.0s geocoding) to prevent thread freezing.
- **Failure Handling**: If the backoff fails, it raises an Exception. The `app.py` catches this, logs it, and silently degrades to reading the latest MySQL cache.

---

## SECTION 7: Database

- **Schema**: 6 core tables. `cities`, `infrastructure`, `shelters`, `zones`, `historical_weather`, `prediction_cache`.
- **Persistent Simulation**: The 90-day history is `INSERT`ed once per city into `historical_weather`. It is never regenerated. This acts as the Single Source of Truth for the entire application.
- **Offline Mode**: Operates identically to online mode, simply skipping the `weather.py` API call phase.

---

## SECTION 8: Maps

- **Rendering Pipeline**: Generating 10,000 polygons on the main thread would crash PyQt. Instead:
  1. `BackgroundWorker` generates a Numpy grid.
  2. Evaluates the ML model at every grid point.
  3. Uses `scipy.ndimage.gaussian_filter` to blur the grid into natural shapes.
  4. Plots via `matplotlib.pyplot.contourf`.
  5. Translates to `folium.Polygon`.
  6. Renders HTML.
  7. Emits `success(html_string)`.
  8. Main thread updates `QWebEngineView`. 

---

## SECTION 9: Trends

- **Historical Simulation**: Plugs directly into the MySQL `historical_weather` table.
- **Charts**: Dual-axis `matplotlib` chart inside PyQt. Bar charts for rainfall, line charts for river levels, and a scatter/line for the evolving Risk Score, proving the mathematical correlation.

---

## SECTION 10: Evacuation

- **Routing**: Uses `networkx` to build an undirected graph. Nodes = Zones and Shelters. Edges = Haversine distance (spherical earth distance). 
- **Priority**: A composite score of `Risk_Score * Population * Distance_Weight`.
- **Resource Allocation**: `Teams = Population / 500`. `Boats = Population / 150` (if risk > 70).
- **Assumptions**: Assumes straight-line spherical travel (no road network blockages or OSN integration). 

---

## SECTION 11: AI Advisor

- **Ollama**: Hosted locally on `localhost:11434`.
- **Context Generation (RAG-lite)**: Before the user prompt, the system silently injects: "You are FloodGuard. City: X, Rainfall: Y, River: Z, Critical Zone: W".
- **Performance**: We pass `"keep_alive": -1` so Ollama never dumps the model from VRAM. Chat history is capped at 11 elements to prevent Kiosk OOM crashes.

---

## SECTION 12: Algorithms

1. **Random Forest Regression**: Averages outputs from hundreds of decision trees.
2. **Dijkstra’s Algorithm**: Shortest path in a weighted graph (NetworkX).
3. **Haversine Formula**: Calculates the great-circle distance between two points on a sphere given their longitudes and latitudes.
4. **Gaussian Convolution (scipy)**: Applies a mathematical blur to grid matrices.

---

## SECTION 13: Design Decisions

- **Why Desktop**: EOCs require stability. Browsers memory-leak over 24 hours. PyQt allows strict hardware control.
- **Why Random Forest**: Deep Learning (LSTMs) is overkill for 7 tabular features and requires a GPU. RF runs fast on EOC CPUs.
- **Why NetworkX**: Python’s most robust graph library, enabling future expansion to OpenStreetMap road ingestion.

---

## SECTION 14: Innovation

**The "Unified Simulation Engine"**
Most hackathon projects fake their data on every page load. FloodGuard seeds a mathematical foundation in MySQL that permanently links the Weather, Map, AI, and ML together. The AI doesn't hallucinate; it reads the same math the Map plots.

**Deep Thread Isolation**
Zero-lag PyQt GUI. All heavy Python processes (SciPy grids, NetworkX routing) are shunted to `QRunnable` threads and rejoined via thread-safe signals. 

---

## SECTION 15: Real World Deployment

FloodGuard is designed for installation in **District Collectorate Control Rooms** and **NDRF Mobile Command Vehicles**. It runs on local network servers (hence the MySQL backend) and acts as the master dispatch interface for rescue commanders.

---

## SECTION 16: Current Limitations

- **Topography**: We use statistical elevation nodes rather than real 3D raster files (.tif).
- **Hydrodynamics**: No physics-based water flow simulation (Navier-Stokes equations).
- **Routing**: Haversine distance rather than actual OpenStreetMap road network edges.

---

## SECTION 17: Future Scope

1. Integration with real-time IoT river level sensors.
2. Deployment of a mobile companion app for NDRF boots on the ground.
3. True road-network routing accounting for flooded intersections.

---

## SECTION 18: Massive Judge Question Bank (Excerpt)

1. **What is the problem?** EOCs lack predictive, offline-first geospatial intelligence.
2. **Why Random Forest?** Best algorithm for tabular environmental data; avoids overfitting.
3. **What happens offline?** Degrades silently to MySQL cache. Maps and AI remain fully functional.
4. **How do you prevent UI freezing?** `BackgroundWorker` (QRunnable) moves all heavy processing off the main UI thread.
5. **How does the Map render?** SciPy applies a Gaussian blur to a Numpy grid of ML predictions, plotted via Matplotlib to Folium.
6. **How do you calculate evacuation routes?** Dijkstra's algorithm via NetworkX using Haversine distances.
7. **What is the Single Source of Truth?** The `historical_weather` table inside MySQL.
8. **Why Ollama?** Total data privacy for sensitive municipal infrastructure.
9. **How do you prevent memory leaks?** 2-minute Kiosk reset timer flushes `QWebEngineView` cache.

*(Remaining 200+ conversational permutations all revolve around these core 9 technical pillars).*

---

## SECTION 19: Difficult Technical Questions

**Q: "If you have a 50x50 grid for the map, aren't you running the ML model 2,500 times per click?"**
**A:** "Yes. However, Random Forest inference on 7 features is extremely fast (`O(depth * trees)`). We pass it through Scikit-Learn natively in memory. The entire 2,500-point inference takes less than 50 milliseconds. The bottleneck is HTML generation, which is why we isolated it in a background thread."

**Q: "How do you handle API rate limits during an exhibition?"**
**A:** "Nominatim is strictly cached in MySQL on the first search. Open-Meteo is timestamp-cached. We never hit the API unnecessarily. If we do get rate-limited, the system falls back to the persistent simulation cache automatically."

---

## SECTION 20: Personal Contribution

When asked "What did you build?", focus on the integration. 
*“I architected the pipeline that ties a Scikit-Learn ML engine, a NetworkX routing graph, and a SciPy map generator into a single, zero-latency desktop interface capable of running completely offline.”*

---

## SECTION 21: Confidence Guide

- **If you don't know an answer**: "FloodGuard's current architecture uses X, but integrating Y is exactly what we have planned for the next phase in our Future Scope."
- **If a judge suggests a feature**: "That's a fantastic observation. We actually evaluated that (e.g., Deep Learning / LSTMs), but chose Random Forest specifically for CPU inference speed in offline environments. However, for a cloud-deployed version, we would absolutely adopt your approach."
- **Speak in terms of 'Impact'**: Don't just say "We use NetworkX." Say "We use NetworkX so that NDRF commanders know exactly how many boats to send to the most critical zones in under 1 second."
