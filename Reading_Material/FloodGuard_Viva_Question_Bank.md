# FloodGuard — Viva Question Bank

> **200 Questions · Beginner → Advanced · Based on Actual Implementation**
>
> Prepared for the Science Exhibition — covering every module, algorithm, service, and design decision in the FloodGuard codebase.

---

## Legend

| Symbol | Difficulty |
|--------|------------|
| 🟢 | Basic |
| 🟡 | Intermediate |
| 🔴 | Advanced |

---

## Project Overview

---

**Q1**
🟢 Basic
**Project Overview**
What is FloodGuard and what problem does it solve?

---

**Q2**
🟢 Basic
**Project Overview**
Who is the intended user of FloodGuard — a general consumer, or a specific type of organization?

---

**Q3**
🟢 Basic
**Project Overview**
What does the term "Emergency Operations Center" (EOC) mean, and how does FloodGuard relate to it?

---

**Q4**
🟡 Intermediate
**Project Overview**
FloodGuard covers five core capabilities. Can you list all of them?

---

**Q5**
🟡 Intermediate
**Project Overview**
Why was FloodGuard built as a desktop application instead of a web application?

---

**Q6**
🟡 Intermediate
**Project Overview**
Which Indian cities are included in the seed dataset, and why were they chosen?

---

**Q7**
🔴 Advanced
**Project Overview**
How does FloodGuard differentiate between "live intelligence" mode and "scenario simulation" mode, and why is this separation important for an EOC?

---

## Problem Statement

---

**Q8**
🟢 Basic
**Problem Statement**
What real-world problem does FloodGuard address in the context of Indian cities?

---

**Q9**
🟢 Basic
**Problem Statement**
Why is flood forecasting important for disaster management authorities?

---

**Q10**
🟡 Intermediate
**Problem Statement**
What limitations of existing flood warning systems does FloodGuard attempt to overcome?

---

**Q11**
🟡 Intermediate
**Problem Statement**
How does FloodGuard address the challenge of operating in areas with poor internet connectivity?

---

## Flood Science

---

**Q12**
🟢 Basic
**Flood Science**
What meteorological factors contribute to urban flooding?

---

**Q13**
🟢 Basic
**Flood Science**
What is the difference between a flash flood and a riverine flood?

---

**Q14**
🟡 Intermediate
**Flood Science**
In FloodGuard's risk model, how is the distinction between "Flash-flood" and "Riverine-flood" patterns determined mathematically?

---

**Q15**
🟡 Intermediate
**Flood Science**
Why does elevation play an important role in flood risk, and how does FloodGuard's risk formula account for it?

---

**Q16**
🔴 Advanced
**Flood Science**
FloodGuard uses the formula `risk = rainfall×0.45 + river_level×11.5 + (60−elevation)×0.35 + flood_freq×28 + (18 if flood else 0)`. Explain the scientific reasoning behind each coefficient and weight.

---

## Historical Floods

---

**Q17**
🟢 Basic
**Historical Floods**
How does FloodGuard use historical flood data in its predictions?

---

**Q18**
🟡 Intermediate
**Historical Floods**
The seed data generates 90 days of synthetic rainfall and river level history per city. What conditions determine whether a day is marked as a "flood occurred" event?

---

**Q19**
🟡 Intermediate
**Historical Floods**
Why do cities like Mumbai, Kochi, and Guwahati have a higher rainfall bias (35 mm) in the synthetic data compared to other cities (22 mm)?

---

**Q20**
🔴 Advanced
**Historical Floods**
How does the `historical_flood_frequency` feature affect the Random Forest model's output, and why is it weighted at 28 in the risk formula?

---

## Existing Systems

---

**Q21**
🟢 Basic
**Existing Systems**
What government agencies in India are responsible for flood warnings?

---

**Q22**
🟡 Intermediate
**Existing Systems**
How does FloodGuard's approach differ from the Central Water Commission's existing flood forecasting methods?

---

**Q23**
🟡 Intermediate
**Existing Systems**
What advantage does FloodGuard's offline fallback mode provide over cloud-only flood monitoring platforms?

---

## Innovation

---

**Q24**
🟢 Basic
**Innovation**
What is unique or innovative about FloodGuard compared to a standard weather app?

---

**Q25**
🟡 Intermediate
**Innovation**
How does the "What-if" scenario simulation feature help emergency planners make decisions?

---

**Q26**
🟡 Intermediate
**Innovation**
Why did you integrate a local AI language model instead of using a cloud-based AI API like ChatGPT?

---

**Q27**
🔴 Advanced
**Innovation**
FloodGuard combines ML risk prediction, graph-based evacuation routing, GIS mapping, and local LLM advisory in a single desktop application. What architectural challenges arise from integrating these four subsystems?

---

## Complete Workflow

---

**Q28**
🟢 Basic
**Complete Workflow**
Describe the step-by-step setup process to run FloodGuard from a fresh clone.

---

**Q29**
🟡 Intermediate
**Complete Workflow**
What happens when a user types a city name in the search bar and presses Enter, in both online and offline modes?

---

**Q30**
🟡 Intermediate
**Complete Workflow**
Trace the complete data flow from when a user adjusts a rainfall slider to when the dashboard displays an updated risk score.

---

**Q31**
🔴 Advanced
**Complete Workflow**
Explain the full lifecycle of a city being added for the first time — from geocoding through weather fetch, data bundle generation, database persistence, map rendering, and risk scoring.

---

## Backend Architecture

---

**Q32**
🟢 Basic
**Backend Architecture**
What programming language and major frameworks does FloodGuard use?

---

**Q33**
🟡 Intermediate
**Backend Architecture**
FloodGuard has two parallel data access layers — `FloodRepository` and `CacheService`. Why do both exist, and how do they differ?

---

**Q34**
🟡 Intermediate
**Backend Architecture**
How does the service layer pattern separate concerns in FloodGuard's backend?

---

**Q35**
🔴 Advanced
**Backend Architecture**
The `cities` table schema differs between `FloodRepository` (using `name`) and `CacheService` (using `city`, plus weather columns). What problems can arise from this dual-schema design, and how would you resolve it?

---

## Folder Structure

---

**Q36**
🟢 Basic
**Folder Structure**
Describe the top-level folder structure of the FloodGuard project and the purpose of each directory.

---

**Q37**
🟡 Intermediate
**Folder Structure**
What is the purpose of the `floodguard/` package directory, and how does it relate to `app.py`?

---

**Q38**
🟡 Intermediate
**Folder Structure**
Why are ML model files stored in a separate `models/` directory rather than inside the `floodguard/` package?

---

## Every Important File

---

**Q39**
🟢 Basic
**Every Important File**
What does the `requirements.txt` file contain, and why are no version pins specified?

---

**Q40**
🟢 Basic
**Every Important File**
What is the purpose of `setup_db.py`?

---

**Q41**
🟡 Intermediate
**Every Important File**
What do `fix_buttons.py` and `fix_theme.py` do, and why could they conflict with each other?

---

**Q42**
🟡 Intermediate
**Every Important File**
What does `seed_data.py` generate, and why does it produce both a MySQL database and a JSON file?

---

**Q43**
🔴 Advanced
**Every Important File**
The `.gitignore` excludes `assets/seed_cache.json` and `logs/*.log`. Why are generated assets excluded from version control, and what are the trade-offs?

---

## app.py

---

**Q44**
🟢 Basic
**app.py**
How many classes are defined in `app.py`, and what is the main application class?

---

**Q45**
🟢 Basic
**app.py**
What are the six tabs/pages in the FloodGuard interface?

---

**Q46**
🟡 Intermediate
**app.py**
What is `CityDistributionModel` and what spatial features does it generate mathematically?

---

**Q47**
🟡 Intermediate
**app.py**
How does `FloodGuardWindow.__init__()` initialize all the services it depends on?

---

**Q48**
🟡 Intermediate
**app.py**
What is the purpose of `QuietWebEnginePage`, and how does it intercept map click events?

---

**Q49**
🔴 Advanced
**app.py**
The `redraw_map()` method is described as the most complex in the codebase. What are the five GIS layers it renders, and how is each one computed?

---

**Q50**
🔴 Advanced
**app.py**
Explain the "Request ID Pattern" used in `self.risk_request_id`. Why is it needed, and what race condition does it prevent?

---

## Services

---

**Q51**
🟢 Basic
**Services**
Name all the service classes used in FloodGuard and their responsibilities.

---

**Q52**
🟡 Intermediate
**Services**
Why are most service methods implemented as static methods or class methods instead of instance methods?

---

**Q53**
🟡 Intermediate
**Services**
How does `CityService.generate_default_city_bundle()` create realistic zone, shelter, and infrastructure data for a newly added city?

---

**Q54**
🔴 Advanced
**Services**
How does `WeatherService.fetch_weather()` implement exponential backoff retry logic, and what specific HTTP status codes trigger retries versus immediate failures?

---

## Repository Pattern

---

**Q55**
🟢 Basic
**Repository Pattern**
What is the Repository Pattern, and why is it used in FloodGuard?

---

**Q56**
🟡 Intermediate
**Repository Pattern**
How does `FloodRepository` implement the MySQL-first, JSON-fallback strategy in its read methods?

---

**Q57**
🟡 Intermediate
**Repository Pattern**
What happens inside `FloodRepository._check_mysql()`, and how does its result affect all subsequent database operations?

---

**Q58**
🔴 Advanced
**Repository Pattern**
When `FloodRepository.add_city()` is called, it writes to JSON first and then attempts MySQL. What consistency issues could arise if the MySQL write fails after the JSON write succeeds?

---

## APIs

---

**Q59**
🟢 Basic
**APIs**
What external APIs does FloodGuard connect to?

---

**Q60**
🟡 Intermediate
**APIs**
FloodGuard uses two different geocoding APIs — Nominatim (OpenStreetMap) in `city_service.py` and Open-Meteo Geocoding in `weather.py`. Why do two different geocoding implementations exist?

---

**Q61**
🟡 Intermediate
**APIs**
What parameters does FloodGuard send to the Open-Meteo Forecast API, and what data does it receive back?

---

**Q62**
🟡 Intermediate
**APIs**
How does FloodGuard query the Overpass (OpenStreetMap) API for real infrastructure data when loading a city in online mode?

---

**Q63**
🔴 Advanced
**APIs**
What is the OSRM (Open Source Routing Machine) API, and how does `RoutingService` use its `/nearest`, `/route`, and `/table` endpoints for evacuation routing?

---

**Q64**
🔴 Advanced
**APIs**
FloodGuard sets a connection timeout of 1 second for MySQL and a read timeout of 5–10 seconds for weather APIs. How do these timeout values affect the user experience and system reliability?

---

## Database

---

**Q65**
🟢 Basic
**Database**
What database does FloodGuard use, and what is the database name?

---

**Q66**
🟢 Basic
**Database**
How many tables are in the FloodGuard database, and what are they named?

---

**Q67**
🟡 Intermediate
**Database**
Describe the schema of the `cities` table and explain the purpose of each column.

---

**Q68**
🟡 Intermediate
**Database**
What foreign key relationships exist between the tables, and in what order must they be dropped?

---

**Q69**
🔴 Advanced
**Database**
The `simulation_logs` table stores `confidence_low`, `confidence_high`, and `mode` (online/offline). How is this data used for audit trails and historical analysis?

---

## MySQL

---

**Q70**
🟢 Basic
**MySQL**
How does FloodGuard connect to MySQL, and where is the password stored?

---

**Q71**
🟡 Intermediate
**MySQL**
What does the `db.py` module's `mysql_connection()` context manager do, and why is it implemented as a context manager?

---

**Q72**
🟡 Intermediate
**MySQL**
How does `CacheService.initialize_db_schema_if_needed()` implement self-healing schema management?

---

**Q73**
🔴 Advanced
**MySQL**
`CacheService.save_city()` uses explicit transaction management with `conn.rollback()` on error. Why is this important, and what could happen without it?

---

## Cache System

---

**Q74**
🟢 Basic
**Cache System**
What is `seed_cache.json`, and what role does it play in the application?

---

**Q75**
🟡 Intermediate
**Cache System**
How does FloodGuard determine whether cached weather data is "stale" and needs refreshing?

---

**Q76**
🟡 Intermediate
**Cache System**
What is the structure of the `seed_cache.json` file, and what five top-level keys does it contain?

---

**Q77**
🔴 Advanced
**Cache System**
`RoutingService` uses `@lru_cache(maxsize=1024)` for memoization. What is LRU caching, how does it work here, and what happens when the cache reaches 1024 entries?

---

## Offline Mode

---

**Q78**
🟢 Basic
**Offline Mode**
What happens when the user toggles FloodGuard into offline mode?

---

**Q79**
🟡 Intermediate
**Offline Mode**
How does the city search behavior differ between online and offline modes?

---

**Q80**
🟡 Intermediate
**Offline Mode**
When the weather API is unavailable, how does the application indicate to the user that it is using cached data?

---

**Q81**
🔴 Advanced
**Offline Mode**
FloodGuard has a multi-strategy internet check — TCP socket to 8.8.8.8, HTTP HEAD to google/github/cloudflare, and a GET to Open-Meteo. Why are three separate strategies needed?

---

## Machine Learning

---

**Q82**
🟢 Basic
**Machine Learning**
What type of machine learning model does FloodGuard use for flood risk prediction?

---

**Q83**
🟢 Basic
**Machine Learning**
What does the ML model predict — a category (flood/no-flood) or a numerical score?

---

**Q84**
🟡 Intermediate
**Machine Learning**
Why was regression chosen over classification for the flood risk model?

---

**Q85**
🟡 Intermediate
**Machine Learning**
What is the complete ML pipeline in FloodGuard, from raw data to prediction output?

---

**Q86**
🔴 Advanced
**Machine Learning**
The training pipeline uses synthetic data augmentation by adding Gaussian noise. Why is this done, and what are the noise parameters (σ) for rainfall and river level?

---

## Scikit-learn

---

**Q87**
🟢 Basic
**Scikit-learn**
What is scikit-learn, and which specific classes from scikit-learn does FloodGuard use?

---

**Q88**
🟡 Intermediate
**Scikit-learn**
The model pipeline uses `StandardScaler` before `RandomForestRegressor`. What does `StandardScaler` do, and is it strictly necessary for a Random Forest?

---

**Q89**
🔴 Advanced
**Scikit-learn**
FloodGuard's model pipeline is `Pipeline([("scaler", StandardScaler()), ("forest", RandomForestRegressor(...))])`. How does scikit-learn's Pipeline ensure that the scaler is fitted only on training data and not on test data during cross-validation?

---

## Random Forest

---

**Q90**
🟢 Basic
**Random Forest**
What is a Random Forest, and how does it make predictions?

---

**Q91**
🟡 Intermediate
**Random Forest**
FloodGuard uses `n_estimators=150` and `min_samples_leaf=3`. What do these hyperparameters control?

---

**Q92**
🟡 Intermediate
**Random Forest**
Why is `random_state=12` set in the RandomForestRegressor, and what would happen if it were removed?

---

**Q93**
🔴 Advanced
**Random Forest**
How does FloodGuard compute confidence intervals from the Random Forest's individual tree predictions, and why is a multiplier of 1.8× standard deviation used with a minimum spread of 5.0?

---

## Decision Trees

---

**Q94**
🟢 Basic
**Decision Trees**
What is a Decision Tree, and how does it relate to a Random Forest?

---

**Q95**
🟡 Intermediate
**Decision Trees**
How does `min_samples_leaf=3` prevent overfitting in each decision tree of the forest?

---

**Q96**
🔴 Advanced
**Decision Trees**
FloodGuard accesses `model.named_steps["forest"].estimators_` to get individual tree predictions. What does this internal attribute contain, and why is accessing individual trees important for uncertainty quantification?

---

## Dataset

---

**Q97**
🟢 Basic
**Dataset**
How many cities, zones, shelters, and infrastructure items are in FloodGuard's seed dataset?

---

**Q98**
🟡 Intermediate
**Dataset**
How is the 90-day rainfall history generated synthetically using Gaussian distributions and seasonal sine waves?

---

**Q99**
🟡 Intermediate
**Dataset**
Why is `random.seed(42)` used in `build_seed_data()`, and what does reproducibility mean in this context?

---

**Q100**
🔴 Advanced
**Dataset**
The training data is augmented from 900 historical rows to 2700 (900 original + 1800 synthetic). Why was a 2× augmentation ratio chosen, and how might this affect model generalization?

---

## Feature Engineering

---

**Q101**
🟢 Basic
**Feature Engineering**
What are the four input features used by the flood risk model?

---

**Q102**
🟡 Intermediate
**Feature Engineering**
Why is `(60 − elevation)` used in the risk formula instead of elevation directly?

---

**Q103**
🟡 Intermediate
**Feature Engineering**
How does FloodGuard compute the "discharge rate" feature using linear regression on recent river level values?

---

**Q104**
🔴 Advanced
**Feature Engineering**
The risk formula adds +18 points if `flood_occurred` is True. This is a binary feature in a regression target. What effect does this have on the model's decision boundaries, and could it introduce bias?

---

## Joblib

---

**Q105**
🟢 Basic
**Joblib**
What is joblib, and why is it used to save the ML model instead of Python's pickle?

---

**Q106**
🟡 Intermediate
**Joblib**
Where is the trained model file stored, and what is its approximate size?

---

**Q107**
🔴 Advanced
**Joblib**
What security risks exist when loading a joblib-serialized model file, and how could a malicious model file compromise the system?

---

## Model Training

---

**Q108**
🟢 Basic
**Model Training**
What command do you run to train the FloodGuard ML model?

---

**Q109**
🟡 Intermediate
**Model Training**
Describe the three steps that `train_model.py` performs from start to finish.

---

**Q110**
🟡 Intermediate
**Model Training**
The synthetic augmentation adds Gaussian noise with σ=10 for rainfall and σ=0.28 for river level. Why are these specific noise levels chosen?

---

**Q111**
🔴 Advanced
**Model Training**
FloodGuard's training pipeline has no train-test split, no cross-validation, and no evaluation metrics. What risks does this pose, and how would you add proper model evaluation?

---

## Model Prediction

---

**Q112**
🟢 Basic
**Model Prediction**
What is a `RiskResult`, and what fields does it contain?

---

**Q113**
🟡 Intermediate
**Model Prediction**
How does `FloodRiskModel.score_zone()` generate a natural-language explanation alongside the numerical score?

---

**Q114**
🟡 Intermediate
**Model Prediction**
What is the difference between zone-level scoring and city-level scoring, and how does `city_score()` aggregate zone results?

---

**Q115**
🔴 Advanced
**Model Prediction**
How does the `_slope()` function use `np.polyfit()` for linear regression to project 3-day rainfall trends, and why is a window of the last 5 data points used?

---

## Confidence Calculation

---

**Q116**
🟡 Intermediate
**Confidence Calculation**
How are confidence intervals (confidence_low and confidence_high) calculated from individual Random Forest tree predictions?

---

**Q117**
🔴 Advanced
**Confidence Calculation**
The confidence spread uses `std × 1.8` with a floor of 5.0. Why is 1.8 used instead of the standard 1.96 for a 95% confidence interval, and what does the minimum spread of 5.0 ensure?

---

## GIS

---

**Q118**
🟢 Basic
**GIS**
What does GIS stand for, and how is it used in FloodGuard?

---

**Q119**
🟡 Intermediate
**GIS**
How does FloodGuard generate contour polygons for its map layers using matplotlib's `contourf` and then convert them to folium polygons?

---

**Q120**
🟡 Intermediate
**GIS**
What is Inverse Distance Weighting (IDW) interpolation, and where is it used in FloodGuard's map rendering?

---

**Q121**
🔴 Advanced
**GIS**
The flood risk layer blends IDW zone interpolation (40%) with model-based risk (60%). Why is a blended approach used instead of purely model-based rendering?

---

## Folium

---

**Q122**
🟢 Basic
**Folium**
What is Folium, and why is it used in FloodGuard?

---

**Q123**
🟡 Intermediate
**Folium**
How does FloodGuard render a Folium map inside a PyQt6 desktop window?

---

**Q124**
🔴 Advanced
**Folium**
FloodGuard uses two different mechanisms to handle map clicks — URL interception (`pyqt://click`) for the GIS map and QWebChannel for the evacuation map. Why are two different approaches used?

---

## Leaflet

---

**Q125**
🟢 Basic
**Leaflet**
What is Leaflet.js, and how does it relate to Folium?

---

**Q126**
🟡 Intermediate
**Leaflet**
What base tile layer does FloodGuard use for its maps, and why was CartoDB Positron chosen?

---

**Q127**
🔴 Advanced
**Leaflet**
How does FloodGuard inject custom JavaScript into the Folium-generated Leaflet map to forward click events back to the Python application?

---

## OpenStreetMap

---

**Q128**
🟢 Basic
**OpenStreetMap**
What is OpenStreetMap, and how does FloodGuard use it?

---

**Q129**
🟡 Intermediate
**OpenStreetMap**
How does FloodGuard query the Overpass API for real-world hospital, school, and power station locations when loading a city?

---

**Q130**
🔴 Advanced
**OpenStreetMap**
When the Overpass API returns fewer infrastructure items than the minimum threshold, FloodGuard auto-generates synthetic entries. How are these synthetic positions calculated, and what minimum counts are enforced?

---

## Open-Meteo

---

**Q131**
🟢 Basic
**Open-Meteo**
What is the Open-Meteo API, and what weather parameters does FloodGuard fetch from it?

---

**Q132**
🟡 Intermediate
**Open-Meteo**
FloodGuard fetches both `current` and `daily` weather data from Open-Meteo. What specific parameters are requested in each category?

---

**Q133**
🔴 Advanced
**Open-Meteo**
`WeatherService` defines five custom exception classes for different failure modes. Name them and explain when each is raised.

---

## Evacuation

---

**Q134**
🟢 Basic
**Evacuation**
What is the purpose of FloodGuard's evacuation planning module?

---

**Q135**
🟡 Intermediate
**Evacuation**
How does the Evacuation Command Portal display its information — what KPI cards, tables, and panels does it contain?

---

**Q136**
🟡 Intermediate
**Evacuation**
How is evacuation priority score calculated, and what three factors determine it?

---

**Q137**
🔴 Advanced
**Evacuation**
How are "Teams Required" and "Boats Required" calculated from the priority score and risk score, and what are the thresholds?

---

## Routing

---

**Q138**
🟢 Basic
**Routing**
How does FloodGuard find the best evacuation route from a zone to a shelter?

---

**Q139**
🟡 Intermediate
**Routing**
What is the difference between the graph-based routing in `evacuation.py` (NetworkX) and the road-based routing in `routing_service.py` (OSRM)?

---

**Q140**
🔴 Advanced
**Routing**
`RoutingService.find_best_shelter()` first attempts the OSRM `/table` endpoint and falls back to individual `/route` calls. Why is the distance matrix approach more efficient?

---

## NetworkX

---

**Q141**
🟢 Basic
**NetworkX**
What is NetworkX, and what type of graph does FloodGuard build with it?

---

**Q142**
🟡 Intermediate
**NetworkX**
How does `EvacuationPlanner.build_graph()` construct the evacuation graph — what are the nodes, edges, and edge weights?

---

**Q143**
🔴 Advanced
**NetworkX**
Each node in the evacuation graph connects to its 4 nearest neighbors. Why 4, and how would increasing or decreasing this connectivity affect evacuation routing?

---

## Dijkstra's Algorithm

---

**Q144**
🟢 Basic
**Dijkstra's Algorithm**
What is Dijkstra's algorithm, and what problem does it solve?

---

**Q145**
🟡 Intermediate
**Dijkstra's Algorithm**
How does FloodGuard use `nx.shortest_path_length()` and `nx.shortest_path()` to find the nearest shelter for each zone?

---

**Q146**
🔴 Advanced
**Dijkstra's Algorithm**
What is the time complexity of Dijkstra's algorithm, and is it efficient enough for FloodGuard's graph size of approximately 90 nodes (60 zones + 30 shelters)?

---

## Haversine Formula

---

**Q147**
🟢 Basic
**Haversine Formula**
What is the Haversine formula, and what does it calculate?

---

**Q148**
🟡 Intermediate
**Haversine Formula**
Write out the Haversine formula as used in FloodGuard's `haversine_km()` function and explain each variable.

---

**Q149**
🔴 Advanced
**Haversine Formula**
The Haversine formula assumes Earth is a perfect sphere with radius 6371 km. What error does this introduce, and would using the Vincenty formula be worthwhile for FloodGuard's use case?

---

## Shelter Selection

---

**Q150**
🟡 Intermediate
**Shelter Selection**
How does FloodGuard filter shelters with available capacity before routing evacuees?

---

**Q151**
🟡 Intermediate
**Shelter Selection**
What are the three shelter types in the seed data, and what are their respective capacities?

---

**Q152**
🔴 Advanced
**Shelter Selection**
What happens if all shelters are at full capacity? How does the EvacuationPlanner handle this edge case?

---

## Resource Allocation

---

**Q153**
🟡 Intermediate
**Resource Allocation**
How does FloodGuard calculate the estimated evacuation time for a zone, given distance and population?

---

**Q154**
🔴 Advanced
**Resource Allocation**
The Commander Recommendation panel generates a bullet-point operational briefing. What data points are combined to produce this recommendation?

---

## AI Advisor

---

**Q155**
🟢 Basic
**AI Advisor**
What is the AI Advisor in FloodGuard, and what role does it play?

---

**Q156**
🟡 Intermediate
**AI Advisor**
What six Quick Action presets are available in the AI Advisor, and what does each one ask the AI to generate?

---

**Q157**
🟡 Intermediate
**AI Advisor**
How does the AI Advisor's system prompt constrain the AI to stay within its professional role and avoid general chat?

---

**Q158**
🔴 Advanced
**AI Advisor**
The system prompt injects ALL live dashboard context — weather, risk scores, zone assignments, infrastructure counts, and slider values. Why is this contextual grounding important for preventing AI hallucination?

---

## Ollama

---

**Q159**
🟢 Basic
**Ollama**
What is Ollama, and why is it used instead of a cloud AI service?

---

**Q160**
🟡 Intermediate
**Ollama**
What is the primary LLM model used by FloodGuard, and what is the fallback model?

---

**Q161**
🟡 Intermediate
**Ollama**
How does FloodGuard attempt to auto-start Ollama if it is not already running?

---

**Q162**
🔴 Advanced
**Ollama**
FloodGuard sends `keep_alive: -1` when preloading the model. What does this parameter do in the Ollama API, and why is it set to negative one?

---

## Prompt Engineering

---

**Q163**
🟡 Intermediate
**Prompt Engineering**
The AI system prompt is approximately 155 lines long. What major sections does it contain?

---

**Q164**
🟡 Intermediate
**Prompt Engineering**
How does the system prompt define the AI's response format template (Assessment/Reasoning/Risk Factors/Recommendations)?

---

**Q165**
🔴 Advanced
**Prompt Engineering**
What specific "hallucination prevention rules" are embedded in the system prompt, and how do they work?

---

## Threading

---

**Q166**
🟢 Basic
**Threading**
Why does FloodGuard need background threads, and what would happen without them?

---

**Q167**
🟡 Intermediate
**Threading**
Describe the `run_background()` method and its four parameters: `task`, `on_success`, `on_error`, and `on_progress`.

---

**Q168**
🔴 Advanced
**Threading**
How does `BackgroundWorker.run()` use `inspect.signature()` to detect whether the task callable accepts a progress callback parameter?

---

## QThreads

---

**Q169**
🟡 Intermediate
**QThreads**
Why does FloodGuard use QThread instead of Python's `threading.Thread`?

---

**Q170**
🟡 Intermediate
**QThreads**
How does `shutdown_workers()` ensure all threads are properly terminated when the application exits?

---

**Q171**
🔴 Advanced
**QThreads**
FloodGuard moves a `BackgroundWorker` QObject to a `QThread` using `moveToThread()`. What thread-safety rules does this impose on signal-slot connections?

---

## Performance

---

**Q172**
🟡 Intermediate
**Performance**
The GIS map renders 60×60 grids for population density and 40×40 grids for flood risk. How do these grid sizes affect rendering performance?

---

**Q173**
🔴 Advanced
**Performance**
How does the use of `scipy.ndimage.gaussian_filter` for smoothing interpolated grids balance visual quality with computational cost?

---

## Error Handling

---

**Q174**
🟢 Basic
**Error Handling**
How does FloodGuard handle the situation where MySQL is not running?

---

**Q175**
🟡 Intermediate
**Error Handling**
What is the "graceful degradation" pattern, and where is it applied in FloodGuard?

---

**Q176**
🔴 Advanced
**Error Handling**
FloodGuard catches `nx.NetworkXNoPath` and `nx.NodeNotFound` during evacuation planning. What scenarios would trigger these exceptions?

---

## Logging

---

**Q177**
🟢 Basic
**Logging**
Where does FloodGuard store its log files, and what format do log entries follow?

---

**Q178**
🟡 Intermediate
**Logging**
What types of events are logged at INFO level versus ERROR level?

---

**Q179**
🔴 Advanced
**Logging**
How could structured logging (JSON-formatted logs) improve FloodGuard's operational monitoring compared to the current plain-text log format?

---

## Software Engineering

---

**Q180**
🟡 Intermediate
**Software Engineering**
What software engineering best practices does FloodGuard follow, and which ones are missing?

---

**Q181**
🔴 Advanced
**Software Engineering**
FloodGuard's `app.py` is approximately 5000 lines in a single file. What are the maintainability risks, and how would you refactor it?

---

## Design Patterns

---

**Q182**
🟢 Basic
**Design Patterns**
What is a "design pattern" in software engineering?

---

**Q183**
🟡 Intermediate
**Design Patterns**
Identify at least five design patterns used in FloodGuard and where each is applied.

---

**Q184**
🔴 Advanced
**Design Patterns**
FloodGuard uses a "Strategy Pattern" with MySQL-first and JSON-fallback. How could this be made more extensible to support additional data sources like SQLite or PostgreSQL?

---

## Architecture

---

**Q185**
🟡 Intermediate
**Architecture**
Draw or describe FloodGuard's layered architecture from UI to database.

---

**Q186**
🔴 Advanced
**Architecture**
How does FloodGuard's architecture compare to a standard MVC (Model-View-Controller) pattern, and where does it deviate?

---

## Security

---

**Q187**
🟡 Intermediate
**Security**
How does FloodGuard handle the MySQL database password — is it hardcoded or externalized?

---

**Q188**
🔴 Advanced
**Security**
FloodGuard connects to the Ollama API on localhost without authentication. What security risks does this pose in a shared network environment?

---

## Reliability

---

**Q189**
🟡 Intermediate
**Reliability**
How does FloodGuard ensure the application remains usable when external services (MySQL, APIs, Ollama) are unavailable?

---

**Q190**
🔴 Advanced
**Reliability**
The MySQL connection timeout is set to 1 second. What trade-off does this represent between responsiveness and reliability?

---

## Real-World Deployment

---

**Q191**
🟡 Intermediate
**Real-World Deployment**
What changes would be needed to deploy FloodGuard in a real government Emergency Operations Center?

---

**Q192**
🔴 Advanced
**Real-World Deployment**
FloodGuard uses synthetic seed data for 10 cities. How would you integrate real-time data feeds from agencies like the India Meteorological Department (IMD) or Central Water Commission (CWC)?

---

## Government Use Cases

---

**Q193**
🟡 Intermediate
**Government Use Cases**
How could NDMA (National Disaster Management Authority) use FloodGuard during an actual flood emergency?

---

**Q194**
🔴 Advanced
**Government Use Cases**
What compliance or certification requirements (e.g., data sovereignty, audit logging) would FloodGuard need to meet for government adoption?

---

## Future Scope

---

**Q195**
🟡 Intermediate
**Future Scope**
What three features would you add to FloodGuard in its next version?

---

**Q196**
🔴 Advanced
**Future Scope**
How could FloodGuard be extended to support multi-city simultaneous monitoring with a centralized command view?

---

**Q197**
🔴 Advanced
**Future Scope**
How would you replace the synthetic training data with real historical flood data, and what data sources would you use?

---

## Personal Contribution

---

**Q198**
🟢 Basic
**Personal Contribution**
What was your specific role in building FloodGuard?

---

**Q199**
🟡 Intermediate
**Personal Contribution**
Which module or feature was the most difficult to implement, and why?

---

## Challenges Faced

---

**Q200**
🟡 Intermediate
**Challenges Faced**
What was the biggest technical challenge you faced during development, and how did you solve it?

---

## Lessons Learned

---

**Q201**
🟡 Intermediate
**Lessons Learned**
What did you learn about integrating machine learning models into a desktop application?

---

**Q202**
🟡 Intermediate
**Lessons Learned**
If you were to start FloodGuard from scratch, what would you do differently?

---

**Q203**
🔴 Advanced
**Lessons Learned**
What did building FloodGuard teach you about the gap between a working prototype and a production-ready system?

---

> **End of Question Bank — 203 Questions**
