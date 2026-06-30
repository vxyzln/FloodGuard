# FloodGuard

**FloodGuard** is a professional-grade Emergency Operations Center (EOC) platform designed to provide dynamic flood risk analysis, real-time map visualizations, and AI-driven evacuation protocols.

Originally developed as an exhibition project, this application simulates a complete disaster management backend, featuring machine learning predictions, interactive UI dashboards, and fully automated evacuation routing algorithms.

---

## 🌟 Key Features

- **Dynamic Interactive Maps**: High-performance spatial maps built with Folium and PyQt6-WebEngine, featuring real-time heatmaps for flood risk, population density, and infrastructure.
- **Machine Learning Integration**: Utilizes a Scikit-Learn `RandomForestRegressor` ensemble wrapped in a scaling pipeline to accurately predict flood risks based on historical weather patterns.
- **Evacuation Command Portal**: Automatically generates prioritized evacuation routes to the nearest shelters, calculating travel times, boats required, and rescue team deployments.
- **Persistent Synthetic Simulation**: A complex background engine dynamically generates incredibly realistic, day-by-day environmental weather trends using autoregressive mean-reverting algorithms.
- **AI Emergency Advisor**: Fully offline integration with `Ollama` running the LLaMA 3 model, providing automated disaster insights securely without any external API calls.
- **Offline Mode**: Operates entirely independently of internet connectivity by utilizing fallback local caches and straight-line heuristic routing.
- **Kiosk Exhibition Mode**: A specialized hardened environment with deep memory garbage collection (`gc`), ensuring absolute stability for 7+ hour continuous presentations.

## 🏗 Technology Stack

- **Core & UI**: Python 3.10+, PyQt6, PyQt6-WebEngine
- **Maps & Spatial**: Folium, OSRM API (Online Mode)
- **Machine Learning**: Scikit-Learn, SciPy, NumPy, Pandas, Joblib
- **Database**: MySQL Server
- **Artificial Intelligence**: Ollama (LLaMA 3)
- **Data APIs**: Open-Meteo

---

## 🚀 Installation & Setup

FloodGuard requires Python, MySQL, and Ollama to run locally.

**1. Clone the Repository:**
```bash
git clone https://github.com/vxyzln/FloodGuard.git
cd FloodGuard
```

**2. Setup Virtual Environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**3. Install Dependencies:**
```bash
pip install -r requirements.txt
```

**4. Start Background Services:**
Ensure your MySQL server is running.
Start the Ollama AI engine in a separate terminal:
```bash
ollama serve
```

---

## 💻 How to Run

Before running the application, ensure your virtual environment is active.

**Standard Desktop Mode**
```bash
python app.py
```

**Kiosk / Exhibition Mode**
*Launches the app in a frameless window with aggressive background memory management.*
```bash
python app.py --kiosk
```

*(Press `Command + Q` or `Alt + F4` to exit Kiosk Mode).*

---

## 📁 Documentation

All technical references, audits, presentation materials, and the complete Startup Guide are located in the `Reading_Material/` directory. If you are a judge or reviewer, please refer to the `FloodGuard_Technical_Audit.md` and `FloodGuard_Judge_Preparation_Handbook.md`.

## ⚠️ Known Limitations
- The application relies heavily on system RAM for generating and rendering multi-layer spatial maps.
- Initial city load times take ~3-4 seconds due to dynamic HTML file generation for the WebEngine map viewer.
- The AI Advisor requires significant local GPU/CPU compute (via Ollama).

## 📄 License
This project is open-source and available under standard academic and portfolio-use licenses. Please refer to the `LICENSE` file for details.
