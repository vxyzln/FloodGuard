# FloodGuard Startup Guide

This guide provides step-by-step instructions for initializing the environment and running FloodGuard from scratch.

## 1. System Requirements
- **Python**: Version 3.10+
- **Database**: MySQL Server
- **AI Engine**: Ollama
- **Storage**: Minimum 2GB free space for maps, models, and dependencies

## 2. Before Starting
Before launching the application, ensure the required background services are running.

### Database
1. Start your local MySQL Server.
2. Verify the database `floodguard` is accessible using the credentials configured in your environment.

### AI Engine (Ollama)
The AI Advisor relies on a local Ollama instance running the `llama3` model.
1. Start the Ollama service:
   ```bash
   ollama serve
   ```
2. If this is your first time, pull the required model:
   ```bash
   ollama run llama3
   ```

## 3. Installation
Follow these steps to set up the Python environment:

1. **Clone the repository** (or navigate to the project directory):
   ```bash
   cd FloodGuard
   ```

2. **Create a Virtual Environment**:
   ```bash
   python3 -m venv venv
   ```

3. **Activate the Virtual Environment**:
   - On **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```
   - On **Windows**:
     ```bash
     venv\Scripts\activate
     ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## 4. Running the Application

Ensure your virtual environment is activated before running the application.

### Standard Desktop Mode
To run the application in standard windowed mode (best for development and standard use):
```bash
python app.py
```

### Kiosk Mode (Exhibition Mode)
For public demonstrations or exhibitions, launch the application in Kiosk Mode. This mode enforces a frameless window, disables standard close buttons, and implements aggressive 15-minute background memory garbage collection for absolute long-term stability.
```bash
python app.py --kiosk
```
*(To exit Kiosk Mode, press `Command + Q` on macOS or `Alt + F4` on Windows).*

## 5. Troubleshooting Common Issues

- **MySQL not running / Database connection issues**: 
  Ensure MySQL is running on port 3306. Check that the credentials in `floodguard/config.py` (or environment variables) match your local setup. If the database schema is missing, run `python setup_db.py`.
- **Ollama unavailable / API timeout**:
  The AI Advisor will fail to load if Ollama is not running in the background. Verify `ollama serve` is active in a separate terminal.
- **Missing Python packages**:
  Ensure your virtual environment is activated (`source venv/bin/activate`) and you have run `pip install -r requirements.txt`. If you run `python app.py` outside the venv, it will fail to find dependencies like `PyQt6`.
- **Offline mode**:
  FloodGuard uses Open-Meteo for live weather and OSRM for dynamic routing. If you have no internet connection, the application will automatically fall back to cached weather data and straight-line heuristic routing.
