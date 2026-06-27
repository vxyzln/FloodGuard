# FloodGuard

**FloodGuard** is a professional desktop-based Flood Monitoring and Emergency Response Platform designed for Emergency Operations Centers (EOCs), Disaster Management Authorities, and Smart City Command Centers.

The platform provides live meteorological intelligence, predictive risk modeling, critical infrastructure mapping, automated evacuation routing, and an integrated local AI Operations Advisor—all operating within a secure, high-contrast command center UI.

---

## 🌪️ Key Capabilities

- **Live Meteorological Tracking**: Integrates with Open-Meteo to fetch real-time rainfall, temperature, humidity, and wind speeds for any city.
- **Predictive Risk Modeling**: Utilizes a trained `scikit-learn` Random Forest model to calculate a 0-100 Flood Risk Score and assigns operational Alert Levels (Green, Yellow, Orange, Red) based on live and historical data.
- **Scenario Simulation**: Allows command staff to override live data using sliders to simulate "What-if" scenarios (e.g., +20% rainfall) without overwriting the live database cache.
- **Automated Evacuation Planning**: Geocodes city zones and automatically routes populations to the safest nearest shelters, calculating resource requirements like Rescue Teams and Transport Boats.
- **Critical Infrastructure Mapping**: Dynamically plots vulnerable infrastructure (Hospitals, Schools, Bridges, Power Stations) onto interactive PyQt6 spatial maps.
- **AI Operations Advisor**: Features a fully integrated local AI (powered by Ollama and `qwen2.5:3b`) acting as a virtual EOC officer. The AI silently ingests live dashboard context (weather, risk scores, evacuation routes) to generate immediate SitReps, Public Warnings, and Action Plans.
- **Offline / Caching Resilience**: Prioritizes MySQL local caching. If APIs fail or the center loses connectivity, FloodGuard seamlessly falls back to cached geographic and weather data.

---

## 💻 Tech Stack

- **Frontend**: Python 3.12, PyQt6, Matplotlib (for spatial UI plotting)
- **Backend**: Python, Requests (Open-Meteo & Nominatim APIs)
- **Database**: MySQL (via `mysql-connector-python`)
- **Machine Learning**: `scikit-learn` (RandomForestRegressor)
- **Local AI**: Ollama (`qwen2.5:3b` / `phi3:mini`)

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.12+
- MySQL Server (Local)
- [Ollama](https://ollama.com/) (For AI Advisor capabilities)

### 1. Clone & Environment
```bash
git clone https://github.com/vxyzln/FloodGuard.git
cd FloodGuard
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Database & Data Seeding
FloodGuard uses a MySQL backend for caching and fast retrieval. The setup scripts will prompt for your MySQL root password if the `FLOODGUARD_DB_PASSWORD` environment variable is not set.

```bash
python setup_db.py
python seed_data.py
```
*(Note: FloodGuard will still operate in a degraded demo mode using local JSON fallbacks if MySQL is entirely unavailable).*

### 3. Machine Learning Model Setup
Train the baseline Risk Model using the historical seed data:
```bash
python train_model.py
```

### 4. Local AI Advisor Setup
Ensure the Ollama application is installed on your machine. FloodGuard is configured to auto-detect and launch the Ollama service in the background, pull the `qwen2.5:3b` model if missing, preload it on startup, and keep it warm (`keep_alive: -1`) to avoid cold-start delays.

To check model status or run it manually:
```bash
ollama run qwen2.5:3b
```

### 5. Launch the Command Center
```bash
python app.py
```

---

## 🛡️ Design Philosophy

FloodGuard was constructed with strict adherence to **EOC Operational Design Guidelines**:
- **Aesthetics**: Cream/Light operational palette (`background: #F8F6F2`, `panel: #FFFFFF`, `border: #D6D3D1`, `accent: #0F766E`, `text: #111827`, `muted: #6B7280`). No gamification, no excessive sci-fi gradients.
- **Workflow**: Absolute separation of Live Intelligence from Scenario Testing.
- **Authority**: The AI Advisor is locked into a professional persona and strictly forbidden from exposing its LLM nature.

---

*Developed for Indian Cities and global Disaster Management Authorities.*

 
