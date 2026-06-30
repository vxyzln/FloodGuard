# FloodGuard: Complete Startup & Exhibition Manual

This is your brief, step-by-step guide to booting up the entire FloodGuard ecosystem for development or your 7-hour exhibition.

## 1. Start the Database (MySQL)
FloodGuard requires a local MySQL database to cache city data, GIS geometry, and offline telemetry.
- **Ensure MySQL is running on your Mac.**
- Open a terminal and start the MySQL service (if it doesn't start automatically on boot):
  ```bash
  mysql.server start
  # or if using Homebrew:
  brew services start mysql
  ```
- *Note: If it's your very first time setting up a new computer, you must run `python setup_db.py` to create the tables and `python seed_data.py` to load the mock data.*

## 2. Start the AI Advisor (Ollama)
The localized AI Advisor runs on an open-weight LLM to guarantee offline privacy during disasters.
- **Ensure the Ollama application is running.** (You should see the little llama icon in your top Mac menu bar).
- If it's not running, open your Terminal and start it:
  ```bash
  ollama serve
  ```
- *Note: FloodGuard requires the `qwen2.5:3b` model. If you haven't downloaded it yet, run `ollama run qwen2.5:3b` once to pull the model to your machine.*

## 3. Activate the Environment
You must run the application inside the Python virtual environment where all dependencies (PyQt6, Scikit-Learn, Folium, Pandas) are installed.
- Open a fresh Terminal.
- Navigate to your project folder:
  ```bash
  cd /Users/dakshjain/Vault/Projects/FloodGuard
  ```
- Activate the virtual environment:
  ```bash
  source venv/bin/activate
  ```

## 4. Launch FloodGuard
Once MySQL, Ollama, and your `venv` are active, you can launch the application. You have two options:

### Option A: Standard Desktop Mode
Use this for regular testing, development, and debugging.
```bash
python app.py
```
- Launches in a standard window with OS borders.
- Press **F11** to instantly toggle fullscreen on and off.
- *No inactivity timer.*

### Option B: True Kiosk Mode (For the Exhibition)
Use this when you are presenting at your booth for 6-7 hours.
```bash
python app.py --kiosk
```
- **Fully Locked Screen:** Launches automatically in a frameless, borderless Full-Screen window.
- **Deep Memory Garbage Collection:** Triggers an aggressive memory cleanup cycle every 15 minutes in the background, ensuring absolutely zero RAM bloat during 7-hour exhibitions.
- **Anti-Close Protection:** If you accidentally press `Alt+F4` or `Cmd+Q`, the system will block the exit and show a strict confirmation dialog to prevent the app from dying mid-demo.
- **Auto-Reset Active:** If no one touches the mouse or keyboard for 2 full minutes, the application automatically clears all search data and resets to the Home Screen so it is fresh for the next judge/attendee.

---

### Quick Troubleshooting / FAQ
- **"The AI Advisor keeps saying 'Error connecting to AI'!"** 
  -> Ollama is not running. Open a terminal and type `ollama serve`.
- **"The app takes a long time to start!"**
  -> Make sure your Wi-Fi is connected, or completely disconnect it. If your Wi-Fi is weak, it spends a few seconds trying to reach the Open-Meteo weather API before falling back to the offline MySQL cache.
- **"The evacuation resource numbers are completely different than yesterday!"**
  -> We upgraded to FV3.1! The Evacuation module now consumes the exact probabilities from the Random Forest Machine Learning Model (`flood_risk_model.joblib`), ensuring it matches the Dashboard perfectly.
  -> The system will automatically run `train_model.py` for you if the model is ever deleted. It takes about 10 seconds to generate 3,600 rows of history and tune the Random Forest.
