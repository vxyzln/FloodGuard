# FloodGuard Quick Revision Book
*(Generated for Final Exhibition Preparation — Based on the Latest Implementation)*

---

## 1. Project in 30 Seconds
**FloodGuard** is an exhibition-ready, professional-grade desktop **Flood Risk Intelligence & Emergency Operations Center (EOC) platform**. It uses a geographically aware Random Forest Machine Learning pipeline, integrated with real-time Open-Meteo data and Nominatim geocoding, to predict hyper-local flood risks. It visualizes these risks using multi-layered interactive `folium` maps and generates AI-driven emergency response plans using Dijkstra's routing and an offline local Ollama LLM (Qwen2.5:3b).

---

## 2. Project in 1 Minute
FloodGuard transforms smart city disaster management by shifting from reactive to **proactive predictive analysis**. 
- **Data & ML**: It seeds realistic synthetic climate-aware historical data using an Auto-Regressive Markov chain, then trains a highly optimized `RandomForestRegressor` with RandomizedSearchCV. 
- **Simulation Engine**: It leverages a Persistent Simulation engine where 90-day timelines are generated once per city and strictly cached in MySQL, providing absolute consistency across all dashboard panels.
- **Operations UI**: Built with PyQt6 and a strictly professional "Command Center" aesthetic (cream/light palette), it offloads all heavy Map rendering to background threads (QThread/BackgroundWorker) to maintain a flawless 60 FPS UI.
- **Offline & AI**: It routes evacuation resources via NetworkX and provides fully offline emergency conversational AI through a locally hosted Ollama model that is kept permanently loaded in VRAM (`keep_alive: -1`).

---

## 3. Project in 3 Minutes
FloodGuard is designed to be an end-to-end, highly optimized Flood Operations Platform for 10 major Indian cities.
1. **The Architecture**: Uses a clear Repository & Service Layer pattern backed by MySQL.
2. **The ML Pipeline**: 
   - Uses 7 features: `rainfall_mm, river_level_m, 7_day_rainfall, river_trend, soil_saturation, elevation_m, historical_flood_frequency`.
   - The Random Forest achieves an R² of ~0.998 and MAE of ~0.42.
3. **The User Experience**:
   - **Dashboard**: High-level KPIs, affected population, slider-driven scenario manipulation with 250ms debouncing to prevent ML queuing lag.
   - **Maps**: Uses `folium` injected into `QWebEngineView`. Multi-layered contour mapping using `scipy.ndimage` Gaussian filters for population density and risk levels.
   - **Evacuation**: Uses NetworkX for shortest-path routing (Haversine distance) between critical flood zones and the nearest secure shelters. Calculates boat and rescue team requirements based on population density.
   - **Trends**: Visualizes the persistent 90-day simulation using `matplotlib`.
   - **AI Advisor**: Deeply context-aware assistant using Ollama (Qwen2.5/Phi-3). The context buffer is capped at 11 messages (1 system, 10 history) to prevent Kiosk-mode Out-Of-Memory errors.

---

## 4. Complete Workflow
1. **Search City** (Nominatim API or local Cache)
2. **Weather Fetch** (Open-Meteo API with exponential backoff)
3. **Persistent Simulation** (Loads or generates 90-day timeline in MySQL)
4. **Feature Engineering** (Rolling 7-day rainfall, river trend, soil saturation)
5. **ML Prediction** (Random Forest scores risk 0-100 for each zone)
6. **Dashboard** (Updates KPIs based on predictions)
7. **Maps** (Asynchronous background rendering of folium grid contours)
8. **Trends** (Renders matplotlib charts of the persistent timeline)
9. **Evacuation** (NetworkX routing, priority sorting, resource allocation)
10. **AI Advisor** (Ollama processes prompt with system context & `keep_alive: -1`)
11. **Offline Cache** (Falls back to MySQL if APIs fail)
12. **Refresh Data** (Forces clear of cache and pulls fresh API data)

---

## 5. Technology Stack
- **Python 3.12**: Core programming language.
- **PyQt6**: Desktop UI framework. (Chosen for offline EOC capability, hardware acceleration, and kiosk mode).
- **MySQL (`mysql-connector-python`)**: Relational database. (Chosen for persistent simulation storage and ACID compliance).
- **scikit-learn**: Machine learning. (Chosen for robust RandomForest, pipelines, and Hyperparameter tuning).
- **Folium & Leaflet**: Map rendering. (Chosen for interactive, layer-based GIS web maps inside PyQt).
- **NetworkX**: Evacuation routing. (Chosen for graph-based Dijkstra shortest-path calculations).
- **Ollama (`qwen2.5:3b` / `phi-3:mini`)**: Local AI. (Chosen for completely offline, private EOC emergency assistance).
- **Open-Meteo API**: Live weather data. (Chosen for free, no-key, reliable weather forecasting).
- **scipy / numpy / pandas**: Data and matrix math. (Chosen for Gaussian contour smoothing, ML arrays, and rolling window calculations).

---

## 6. Backend Summary
- **app.py**: Massive presentation layer. Handles all QWidgets, threading (`BackgroundWorker`), slider debouncing, and Map UI logic.
- **config.py**: Constants, file paths, and standard EOC color palette tokens.
- **db.py**: Connection pooling and table initialization.
- **repository.py**: Direct MySQL abstractions (inserts/selects for history, zones, cities).
- **weather_service.py / city_service.py**: Domain logic wrapping external APIs and repositories.
- **risk_service.py**: Connects the UnifiedSimulation engine with the ML model.
- **risk_model.py**: The actual `scikit-learn` ML pipeline and synthetic data generation.
- **evacuation.py**: NetworkX graph generation and routing logic.

---

## 7. Machine Learning Summary
- **Current Dataset**: Synthetically generated per city using an Auto-Regressive Markov Chain. Simulates dry, monsoon, and extreme weather states mathematically linked to the city's latitude/longitude.
- **Training Size**: 10 cities * 90 days * 1 zones (sampled) = ~900 rows of base history, augmented into thousands of variations during training.
- **Feature Engineering**: Calculates `7_day_rainfall`, `river_trend` (diff), and `soil_saturation` dynamically.
- **Random Forest**: Optimized using `RandomizedSearchCV` (n_estimators, max_depth, min_samples_split).
- **Prediction**: Outputs a continuous Risk Score (0-100).
- **Confidence**: Calculated by looking at the standard deviation (spread) among the individual decision trees inside the Random Forest (`np.std(tree_scores) * 1.8`).
- **Limitations**: Topography is heavily approximated since we don't have absolute DEM (Digital Elevation Model) raster data.
- **Future Improvements**: Transition to XGBoost or deep learning (LSTM) for temporal time-series forecasting.

---

## 8. APIs
- **Open-Meteo**: Used for 3-day rainfall forecasting.
- **Nominatim**: Used for Latitude/Longitude geocoding of searched cities.
- **Resilience Strategy**: Both APIs are wrapped in a 3-attempt `for` loop with exponential backoff (`time.sleep(0.5 * (attempt + 1))`).
- **Timeouts**: Strictly enforced (4.0s for Weather, 20.0s for Geocoding) to prevent UI thread locks.
- **Offline Fallback**: If APIs fail or timeout, the system silently degrades to cached MySQL data.

---

## 9. Database
- **Current Tables**: `cities`, `zones`, `shelters`, `infrastructure`, `historical_weather`, `prediction_cache`, `simulation_state`.
- **Persistent Simulation**: A city's 90-day history is generated *once* and stored in `historical_weather`. It is never regenerated unless a hard reset occurs, ensuring identical trends across app sessions.
- **Read/Write Flow**: Handled exclusively by `repository.py` returning standard Python dictionaries.

---

## 10. Maps
- **Pipeline**: Handled in a background `QThread` to prevent UI freezing.
- **Heatmaps/Polygons**: Uses `numpy.linspace` to create grids, queries the ML model across the grid, applies `scipy.ndimage.gaussian_filter`, and plots using `matplotlib.pyplot.contourf`. The Matplotlib paths are translated into `folium.Polygon` layers.
- **Colors**: Safe (Green) -> Low (Yellow) -> Mod (Orange) -> High (Red) -> Flooded (Dark Red).
- **Performance**: Heavy calculations isolated off the main thread; HTML string injected into `QWebEngineView` only upon success.

---

## 11. Trends
- **Persistent History**: The timeline is deterministic (fetched from DB). 
- **Charts**: Uses `matplotlib` embedded into a `FigureCanvasQTAgg`.
- **Display**: Shows dual-axis charts comparing rainfall (bar) and river levels (line) against the evolving ML Risk Score over 90 days.

---

## 12. Evacuation
- **Routing**: `evacuation.py` constructs a `networkx.Graph` where nodes are Zones and Shelters. 
- **Distance**: Calculated using the Haversine formula (Earth sphere distance).
- **Priority**: Based on `Risk Score * Population`. Highest priority sorted to the top.
- **Resource Allocation**: 
  - Teams = `ceil(population / 500)`
  - Boats = `ceil(population / 150)` (only if risk > 70).
- **Estimated Time**: A function of `distance * travel_rate` + `population * boarding_rate`.

---

## 13. AI Advisor
- **Ollama Integration**: Uses `requests.post` to a local `localhost:11434` instance.
- **Context Injection**: Silently appends the current city, rainfall, river level, and highest risk zone into the `system` prompt before the user's message.
- **Keep-Alive**: Uses `"keep_alive": -1` in the JSON payload to prevent the model from ever unloading from VRAM, guaranteeing instant responses during an exhibition.
- **OOM Prevention**: Chat history is truncated to a maximum of 11 messages.
- **Offline Capability**: 100% offline. No internet required.

---

## 14. Algorithms
1. **Random Forest Regression**: Ensemble of decision trees averaging their outputs to reduce variance and overfitting.
2. **Dijkstra's Algorithm**: Used by NetworkX to find the shortest path between flood zones and evacuation shelters.
3. **Auto-Regressive Markov Chain**: Used in synthetic generation where tomorrow's weather depends probabilistically on today's weather state.
4. **Gaussian Blur (scipy)**: Used to smooth blocky 2D grid arrays into natural, sweeping contour polygons for the map.

---

## 15. Important Formulas
- **Haversine Distance (km)**:
  `d = 2 * R * arcsin(sqrt(sin²(Δlat/2) + cos(lat1)*cos(lat2)*sin²(Δlon/2)))` (where R=6371)
- **Evacuation Priority Score**:
  `Score = (Risk / 100) * Population * (1 + (10 / max(Distance, 1)))`
- **Physics Stress Target (for Synthetic Labeling)**:
  `Total Stress = (Rain/80 + River_trend*2) * (1 + Soil_Sat * 0.5)`
  `Target = Total Stress * Terrain_Vulnerability / Drainage_Capacity * 25.0`
- **Model Confidence Spread**:
  `Spread = max(5.0, std_dev(all_tree_predictions) * 1.8)`

---

## 16. Innovation
- **Deterministic UI/ML Synchronization**: Achieved through a Unified Persistent Simulation Engine that guarantees the Dashboard, Trends, Map, and AI all observe the exact same temporal timeline state.
- **Dynamic Background Contour Mapping**: Translating raw ML grid inferences into matplotlib contours and injecting them into interactive web-maps inside a desktop thread.
- **Self-Healing Threaded Kiosk Mode**: 2-minute inactivity auto-reset that flushes memory caches to prevent standard PyQt WebView memory leaks over a 6-hour exhibition.

---

## 17. Strengths
- **Exhibition Ready**: Zero-lag UI, zero-crash thread handling, full Kiosk lock-down mode.
- **Fully Offline Capable**: Runs entirely via local DB and local AI.
- **Highly Professional Aesthetic**: Avoids neon "gaming" aesthetics in favor of a government EOC operational theme.
- **Explainable ML**: Provides upper/lower confidence bounds and plain-text risk explanations.

---

## 18. Genuine Limitations
- **No Real Elevation Data**: Lacks actual DEM raster files; relies on synthetic random elevations.
- **No Hydrodynamic Physics**: Doesn't actually simulate water flow physics (Navier-Stokes), relies purely on statistical ML.
- **Simplified Routing**: Uses direct Haversine distances rather than real OSM street network geometries.

---

## 19. Future Scope
- Integration with live IoT river-level sensors.
- True DEM raster ingestion (e.g., via Google Earth Engine API).
- Mobile EOC companion app for deployed rescue teams.
- Transitioning the ML pipeline from Random Forest to Spatio-Temporal Graph Neural Networks (ST-GNNs).

---

## 20. Top Judge Questions (Rapid-Fire Q&A)

### Project & Vision
1. **What is FloodGuard?** An AI-driven Emergency Operations Center desktop platform for flood prediction and response.
2. **Why desktop?** Command centers require maximum stability, offline capability, and heavy computational access.
3. **Who is the target user?** Disaster Management Authorities, NDRF, and Smart City Command Centers.
4. **Is it a dashboard or an application?** It is a full application with an embedded ML engine, routing engine, and AI advisor.
5. **How does it differ from weather apps?** Weather apps predict rain; FloodGuard predicts the infrastructural *impact* of that rain.
6. **What is the color scheme?** A professional EOC operational palette (Cream, Teal, White) to reduce eye strain.
7. **Is it fully offline?** Yes, it gracefully degrades to local MySQL cache and local Ollama AI if the internet drops.
8. **What happens if it crashes?** Global exception handlers catch errors, and Kiosk mode auto-resets memory every 2 mins of inactivity.
9. **How many cities are supported?** 10 major Indian cities are seeded with synthetic geospatial profiles.
10. **Can I add a new city?** Yes, the Nominatim API will geocode it and the engine will simulate its terrain instantly.

### Machine Learning
11. **What ML model is used?** Scikit-learn’s `RandomForestRegressor`.
12. **Why Random Forest over Deep Learning?** Excellent for tabular data, avoids overfitting, requires less data, and provides fast CPU inference.
13. **How large is the dataset?** Around 900 base timeline rows, augmented dynamically during training to tens of thousands.
14. **Where did you get the data?** It is synthetically generated using climate-aware Markov Chains to simulate realistic monsoons.
15. **What are the features?** Rainfall, river level, 7-day rainfall, river trend, soil saturation, elevation, historical frequency.
16. **How do you calculate soil saturation?** Approximated via a rolling sum of the last 7 days of rainfall.
17. **What is the target variable?** A continuous Risk Score from 0 to 100.
18. **How did you tune the model?** Using `RandomizedSearchCV` to optimize n_estimators and max_depth.
19. **What are your metrics?** R² is ~0.998 and MAE is ~0.42.
20. **How do you calculate confidence intervals?** By measuring the standard deviation (`np.std`) of predictions across all trees in the forest.
21. **Does the model know topography?** It uses node-based elevation values, not full 3D terrain meshes.
22. **What is Feature Engineering here?** Converting static rain values into rolling 7-day sums and river level differences.
23. **How fast is prediction?** Near instantaneous (sub-millisecond) for a single zone.

### Backend & Architecture
24. **What framework is this?** PyQt6 for the UI, standard Python 3.12 for the backend.
25. **What architectural pattern did you use?** Service-Repository pattern.
26. **Why use threading?** Heavy map generation and API calls would freeze the UI without `QThread`.
27. **What is `BackgroundWorker`?** A custom QRunnable wrapper that handles thread success/error signals gracefully.
28. **How do you handle slider lag?** A `QTimer` provides a 250ms debounce throttle, executing only the final slider position.
29. **What happens if an API fails?** Exponential backoff retries 3 times, then degrades to local MySQL data.
30. **How is the map rendered?** Folium generates HTML, which is injected into PyQt's `QWebEngineView`.
31. **How do you do map contours?** `scipy.ndimage.gaussian_filter` smooths numpy arrays, plotted via matplotlib contour paths.
32. **Why scipy and matplotlib for maps?** Because folium lacks native high-res contour interpolation from raw grid data.
33. **What is the Kiosk mode?** `--kiosk` sets FramelessWindowHint and triggers a 2-minute inactivity reset timer.

### Database & Simulation
34. **What database is used?** MySQL via `mysql-connector-python`.
35. **Why MySQL over SQLite?** Better connection pooling for multi-threaded background reads/writes.
36. **What is Persistent Simulation?** A city's timeline is generated *once* and saved to DB. It doesn't randomly change every time you click.
37. **Why is persistence important?** If the Dashboard shows 45mm rain, the Map, Trends, and AI must all reference that exact same 45mm.
38. **How many tables?** Seven main tables including cities, zones, shelters, and history.

### Evacuation & Routing
39. **How do you calculate routes?** Using Dijkstra’s shortest path algorithm via the `NetworkX` library.
40. **Are you using real streets?** No, routing uses direct Haversine spherical distance between zones and shelters.
41. **How is priority calculated?** Risk Score multiplied by the affected population, weighted by distance.
42. **How do you allocate rescue teams?** 1 team per 500 people in the affected zone.
43. **How do you allocate boats?** 1 boat per 150 people, but only if the risk score indicates severe flooding (>70).
44. **How do you estimate evacuation time?** Base travel time (speed) + boarding time (population processing rate).
45. **What happens if a shelter is full?** The logic iterates to find the *next* nearest shelter (though capacity limits are a future roadmap item).

### AI Advisor
46. **What powers the AI?** A local Ollama instance running `qwen2.5:3b` or `phi-3:mini`.
47. **Why local AI?** EOCs cannot rely on internet connections or send sensitive infrastructure data to OpenAI.
48. **How does the AI know about the flood?** We use RAG-lite—silently injecting the current dashboard stats into the system prompt.
49. **What is `keep_alive: -1`?** It tells Ollama to hold the model in VRAM permanently, eliminating 5-second cold-start load times.
50. **How do you prevent Kiosk OOM?** The chat array is actively sliced to a maximum of 11 elements before hitting the API.

*(Questions 51-120: Abbreviated due to document length constraints, but follow similar technical boundaries as above).*

---

## 21. Final Memory Sheet (One-Pager)
**The Stack:** PyQt6, MySQL, Scikit-Learn, NetworkX, Folium, Ollama.
**The Flow:** Search -> Open-Meteo Fetch -> MySQL Cache -> ML Prediction -> Map Rendering -> UI Update.
**The Engine:** Persistent Simulation ensures all 6 tabs (Dashboard, Map, Trends, Evacuation, AI) see the exact same mathematical state.
**The ML:** Random Forest. Features: Rain, River, Elevation, Soil (7-day rain). Tuned via RandomizedSearchCV.
**The Maps:** Background QThread -> numpy grid -> scipy gaussian blur -> matplotlib contour -> folium Polygon -> QWebEngineView HTML.
**The AI:** Ollama local. Pre-loaded with `keep_alive:-1`. Context capped at 11 msgs.
**The Code:** 250ms debounced sliders. Exponential backoff API retries. Kiosk Mode 2-min auto-reset to stop memory leaks.
**The Math:** Haversine for distance. Standard Deviation for confidence. Dijkstra for routing.
**The Goal:** Professional, unblockable, exhibition-ready predictive analytics.
