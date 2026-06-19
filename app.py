from __future__ import annotations

from datetime import datetime
import sys
import os
import logging
import socket
import numpy as np
import requests
import folium
import folium.plugins
import matplotlib
import math
import random

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.image as mpimg

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QDialog,
)
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

from floodguard.config import CACHE_PATH, MODEL_PATH, PALETTE, ROOT
from floodguard.evacuation import EvacuationPlanner
from floodguard.map_assets import ensure_placeholder_maps
from floodguard.risk_model import RiskResult, train_and_save_model
from floodguard.seed_definitions import alert_level, build_seed_data
from floodguard.city_service import CityService
from floodguard.weather_service import WeatherService
from floodguard.cache_service import CacheService
from floodguard.risk_service import RiskService

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/floodguard.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FloodGuard")

def check_internet(host="8.8.8.8", port=53, timeout=3.0) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

def check_api_availability(timeout=1.5) -> bool:
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 0, "longitude": 0}, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class CityDistributionModel:
    def __init__(self, city_lat: float, city_lon: float, base_elev: float):
        self.city_lat = city_lat
        self.city_lon = city_lon
        self.base_elev = base_elev
        
        # Define 3 population clusters (center, west suburb, east suburb)
        self.clusters = [
            {"lat": city_lat, "lon": city_lon, "weight": 1.0, "sigma": 0.04},
            {"lat": city_lat + 0.045, "lon": city_lon - 0.05, "weight": 0.6, "sigma": 0.025},
            {"lat": city_lat - 0.05, "lon": city_lon + 0.045, "weight": 0.5, "sigma": 0.025}
        ]
        
        # Major roads modeled as simple lines (lat = m*lon + c)
        self.road1_m = 3.0
        self.road1_c = city_lat - self.road1_m * city_lon
        
        self.road2_m = -0.3
        self.road2_c = city_lat - self.road2_m * city_lon

    def get_population_density(self, lat: float, lon: float) -> float:
        val = 0.0
        for c in self.clusters:
            d2 = (lat - c["lat"])**2 + (lon - c["lon"])**2
            val += c["weight"] * math.exp(-d2 / (2.0 * c["sigma"]**2))
            
        dist_road1 = abs(self.road1_m * lon - lat + self.road1_c) / math.sqrt(self.road1_m**2 + 1)
        dist_road2 = abs(self.road2_m * lon - lat + self.road2_c) / math.sqrt(self.road2_m**2 + 1)
        road_proximity = math.exp(-min(dist_road1, dist_road2)**2 / (2.0 * 0.015**2))
        
        density = 0.8 * val + 0.2 * road_proximity
        noise = 0.03 * (math.sin(100.0 * lat) * math.cos(100.0 * lon))
        return max(0.01, min(1.0, density + noise))

    def get_river_distance(self, lat: float, lon: float) -> float:
        river_lat = self.city_lat + 0.035 * math.sin(18.0 * (lon - self.city_lon)) + 0.01 * (lon - self.city_lon)
        return abs(lat - river_lat)

    def get_elevation(self, lat: float, lon: float) -> float:
        dist_river = self.get_river_distance(lat, lon)
        valley_effect = 1.0 - math.exp(-dist_river**2 / (2.0 * 0.02**2))
        
        slope = (lat - (self.city_lat - 0.15)) + (lon - (self.city_lon - 0.15))
        slope_factor = max(0.1, min(1.0, slope / 0.6))
        
        elev = self.base_elev * (0.3 + 0.7 * valley_effect * slope_factor)
        terrain_noise = 3.0 * math.sin(50.0 * lat) * math.cos(50.0 * lon)
        return max(1.0, elev + terrain_noise)

    def get_flood_risk(self, lat: float, lon: float, rainfall: float, river_level: float) -> float:
        dist_river = self.get_river_distance(lat, lon)
        elev = self.get_elevation(lat, lon)
        
        river_influence_range = 0.02 + 0.01 * max(0.0, river_level - 1.5)
        river_risk = math.exp(-dist_river**2 / (2.0 * river_influence_range**2))
        
        elev_risk = math.exp(-elev / 15.0)
        
        rain_factor = max(0.0, rainfall / 100.0)
        accumulation_risk = rain_factor * (1.0 - math.exp(-dist_river / 0.04)) * elev_risk
        
        base_risk = 0.4 * river_risk + 0.4 * elev_risk + 0.2 * accumulation_risk
        risk_score = base_risk * 100.0
        
        boost = 0.3 * rainfall + 5.0 * max(0.0, river_level - 2.0)
        risk_score = min(100.0, max(0.0, risk_score + boost))
        return risk_score
        
    def get_historical_flood_frequency(self, lat: float, lon: float) -> float:
        dist_river = self.get_river_distance(lat, lon)
        elev = self.get_elevation(lat, lon)
        
        freq = math.exp(-dist_river**2 / (2.0 * 0.018**2)) * math.exp(-elev / 20.0)
        return freq * 1.2

def interpolate_grid(zones, values, lat_min, lat_max, lon_min, lon_max, grid_size=40, power=2.0, sigma=2.0):
    if not zones or not values:
        return []
        
    lats = np.linspace(lat_min, lat_max, grid_size)
    lons = np.linspace(lon_min, lon_max, grid_size)
    
    zone_coords = np.array([[float(z["latitude"]), float(z["longitude"])] for z in zones])
    zone_vals = np.array(values)
    
    grid_vals = np.zeros((grid_size, grid_size))
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            dists = np.sqrt(np.sum((zone_coords - np.array([lat, lon]))**2, axis=1))
            zero_dist_idx = np.where(dists < 1e-6)[0]
            if len(zero_dist_idx) > 0:
                grid_vals[i, j] = zone_vals[zero_dist_idx[0]]
            else:
                weights = 1.0 / (dists ** power)
                grid_vals[i, j] = np.sum(weights * zone_vals) / np.sum(weights)
                
    from scipy.ndimage import gaussian_filter
    smoothed_grid = gaussian_filter(grid_vals, sigma=sigma)
    
    grid_points = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            grid_points.append([lat, lon, float(smoothed_grid[i, j])])
            
    return grid_points

class QuietWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None, click_handler=None):
        super().__init__(parent)
        self.click_handler = click_handler

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        pass

    def acceptNavigationRequest(self, url, navigationType, isMainFrame):
        url_str = url.toString()
        if url_str.startswith("pyqt://click"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url_str)
            params = parse_qs(parsed.query)
            try:
                lat = float(params.get("lat", [0.0])[0])
                lng = float(params.get("lng", [0.0])[0])
                if self.click_handler:
                    self.click_handler(lat, lng)
            except Exception as e:
                logger.error(f"Error handling map click: {e}")
            return False
        return True


STYLE = f"""
QMainWindow, QWidget {{
    background: {PALETTE['background']};
    color: {PALETTE['text']};
    font-family: "SF Pro Text", "Helvetica Neue", "Arial", sans-serif;
    font-size: 14px;
}}
QFrame#Card {{
    background: {PALETTE['panel']};
    border: 1px solid {PALETTE['border']};
    border-radius: 12px;
}}
QPushButton {{
    background: {PALETTE['accent']};
    color: #FFFFFF;
    border: 0;
    padding: 9px 16px;
    border-radius: 8px;
    font-weight: 600;
    font-family: "SF Pro Text", "Helvetica Neue";
}}
QPushButton:hover {{
    background: {PALETTE['accent_hover']};
}}
QPushButton:disabled {{
    background: {PALETTE['border']};
    color: {PALETTE['muted']};
}}
QComboBox, QLineEdit, QTextEdit {{
    background: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 8px;
    color: {PALETTE['text']};
    font-family: "SF Pro Text", "Helvetica Neue";
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {PALETTE['border']};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {PALETTE['accent']};
    width: 18px;
    margin: -7px 0;
    border-radius: 9px;
}}
QTableWidget {{
    background: {PALETTE['panel']};
    alternate-background-color: {PALETTE['surface']};
    color: {PALETTE['text']};
    gridline-color: {PALETTE['border']};
    border: 1px solid {PALETTE['border']};
    font-family: "SF Pro Text", "Helvetica Neue";
    selection-background-color: {PALETTE['accent_hover']};
    selection-color: #FFFFFF;
}}
QTableWidget::item {{
    padding: 8px;
}}
QHeaderView::section {{
    background: {PALETTE['panel']};
    color: {PALETTE['muted']};
    padding: 8px;
    border: 1px solid {PALETTE['border']};
    font-weight: bold;
}}
QFrame#TopNav {{
    background: {PALETTE['panel']};
    border-bottom: 1px solid {PALETTE['border']};
}}
QPushButton#NavButton {{
    background: transparent;
    color: {PALETTE['muted']};
    border: 0;
    border-radius: 8px;
    padding: 8px 14px;
    font-family: "SF Pro Text", "Helvetica Neue";
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#NavButton[active="true"] {{
    background: {PALETTE['background']};
    color: {PALETTE['text']};
    border: 1px solid {PALETTE['border']};
}}
QCheckBox#ModeToggle {{
    color: {PALETTE['text']};
    font-size: 14px;
    font-weight: 600;
    font-family: "SF Pro Text", "Helvetica Neue";
    spacing: 8px;
}}
QCheckBox#ModeToggle::indicator {{
    width: 46px;
    height: 26px;
}}
QCheckBox#ModeToggle::indicator:unchecked {{
    border-radius: 13px;
    background: {PALETTE['border']};
    border: 1px solid {PALETTE['muted']};
}}
QCheckBox#ModeToggle::indicator:checked {{
    border-radius: 13px;
    background: {PALETTE['green']};
    border: 1px solid {PALETTE['green']};
}}
"""


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    label = QLabel(title)
    label.setStyleSheet('font-family: "SF Pro Display", "Helvetica Neue"; font-size: 16px; font-weight: 600; letter-spacing: 1px;')
    layout.addWidget(label)
    return frame, layout


class MplCanvas(FigureCanvas):
    def __init__(self) -> None:
        self.figure = Figure(facecolor=PALETTE["panel"], tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setStyleSheet(f"background: {PALETTE['panel']};")


class BackgroundWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, task) -> None:
        super().__init__()
        self.task = task

    def run(self) -> None:
        try:
            self.finished.emit(self.task())
        except Exception as exc:
            self.failed.emit(str(exc))


from PyQt6.QtWidgets import QDialog

class AlertDetailsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alert System Information")
        self.resize(600, 480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {PALETTE['background']};
            }}
            QLabel {{
                color: {PALETTE['text']};
                font-family: 'SF Pro Text', sans-serif;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        title = QLabel("Emergency Alert Protocol")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: " + PALETTE["accent"] + ";")
        layout.addWidget(title)
        
        # 4 Alert Level cards
        levels = [
            {
                "title": "GREEN ALERT",
                "range": "0–50 Risk Score",
                "meaning": "Low flood probability.",
                "action": "Continue monitoring.",
                "bg": PALETTE["green"],
                "fg": "#FFFFFF"
            },
            {
                "title": "YELLOW ALERT",
                "range": "50–70 Risk Score",
                "meaning": "Potential flooding risk.",
                "action": "Prepare emergency resources.",
                "bg": PALETTE["yellow"],
                "fg": "#111111"
            },
            {
                "title": "ORANGE ALERT",
                "range": "70–90 Risk Score",
                "meaning": "High flood probability.",
                "action": "Prepare evacuation operations.",
                "bg": PALETTE["orange"],
                "fg": "#FFFFFF"
            },
            {
                "title": "RED ALERT",
                "range": "90–100 Risk Score",
                "meaning": "Severe flood threat.",
                "action": "Immediate evacuation recommended.",
                "bg": PALETTE["red"],
                "fg": "#FFFFFF"
            }
        ]
        
        for lvl in levels:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {lvl['bg']};
                    border-radius: 8px;
                    border: none;
                }}
            """)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            
            badge_layout = QVBoxLayout()
            lbl_title = QLabel(lvl["title"])
            lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {lvl['fg']};")
            lbl_range = QLabel(lvl["range"])
            lbl_range.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {lvl['fg']}; opacity: 0.85;")
            badge_layout.addWidget(lbl_title)
            badge_layout.addWidget(lbl_range)
            badge_layout.addStretch()
            
            info_layout = QVBoxLayout()
            lbl_meaning = QLabel(f"<b>Meaning:</b> {lvl['meaning']}")
            lbl_meaning.setStyleSheet(f"font-size: 13px; color: {lvl['fg']};")
            lbl_action = QLabel(f"<b>Recommended Action:</b> {lvl['action']}")
            lbl_action.setStyleSheet(f"font-size: 13px; color: {lvl['fg']};")
            info_layout.addWidget(lbl_meaning)
            info_layout.addWidget(lbl_action)
            
            card_layout.addLayout(badge_layout, 1)
            card_layout.addLayout(info_layout, 2)
            layout.addWidget(card)
            
        layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {PALETTE['accent']};
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['accent_hover']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class FloodGuardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Initialize services
        self.city_service = CityService()
        self.weather_service = WeatherService()
        self.cache_service = CacheService()
        self.risk_service = RiskService()

        self.online_mode = False
        self.using_cached = False
        self.current_city = None
        self.cities_list: list[dict] = []
        self.current_zones: list[dict] = []
        self.current_shelters: list[dict] = []
        self.current_infra: list[dict] = []
        self.current_history: list[dict] = []
        self.current_historical_flood_points: list[dict] = []
        self.current_model: CityDistributionModel | None = None
        self.zone_results: dict[int, RiskResult] = {}
        self.zone_scores: dict[int, float] = {}
        self.city_result = RiskResult(0, 0, 0, "Riverine-flood pattern", 0, "", "")
        self.planner: EvacuationPlanner | None = None
        self.last_data_update: datetime | None = None
        self.active_threads: list[QThread] = []
        self.active_workers: list[BackgroundWorker] = []
        self.risk_request_id = 0
        
        # Real and Scenario Data separation variables
        self.real_rainfall = 0.0
        self.real_river_level = 0.0
        self.real_temperature = 0.0
        self.real_humidity = 0.0
        self.real_wind_speed = 0.0
        self.scenario_rainfall = 0.0
        self.scenario_river_level = 0.0
        self.active_model: str | None = None
        self.ai_messages: list[dict] = []
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.aboutToQuit.connect(self.shutdown_workers)

        self.setWindowTitle("FloodGuard")
        self.resize(1360, 860)
        self.setStyleSheet(STYLE)
        shell = QWidget()
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav_buttons: list[QPushButton] = []
        root.addWidget(self.build_top_nav())
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.build_home()
        self.build_dashboard()
        self.build_map()
        self.build_evacuation()
        self.build_trends()
        self.build_advisor()
        self.show_screen(0)
        self.start_initialization()
        
        for i in range(1, 7):
            shortcut = QShortcut(QKeySequence(str(i)), self)
            shortcut.activated.connect(lambda idx=i-1: self.show_screen(idx))

    def mousePressEvent(self, event):
        focus_widget = QApplication.focusWidget()
        if focus_widget:
            focus_widget.clearFocus()
        super().mousePressEvent(event)

    def build_top_nav(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("TopNav")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(22, 12, 22, 12)
        layout.setSpacing(8)
        for index, label in enumerate(["Home", "Dashboard", "Map", "Evacuation", "Trends", "AI Advisor"]):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setProperty("active", "false")
            button.clicked.connect(lambda checked=False, idx=index: self.show_screen(idx))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch()
        self.mode_toggle = QCheckBox("Offline Mode")
        self.mode_toggle.setObjectName("ModeToggle")
        self.mode_toggle.stateChanged.connect(self.toggle_online)
        layout.addWidget(self.mode_toggle)
        return nav

    def show_screen(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for idx, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if idx == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 2:
            self.redraw_map()
        if index == 3:
            self.refresh_evacuation()
        if index == 4:
            self.refresh_trends()

    def run_background(self, task, on_success, on_error=None) -> None:
        thread = QThread(self)
        worker = BackgroundWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_success)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(on_error or self.handle_background_error)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(lambda: self.active_threads.remove(thread) if thread in self.active_threads else None)
        thread.finished.connect(lambda: self.active_workers.remove(worker) if worker in self.active_workers else None)
        thread.finished.connect(thread.deleteLater)
        self.active_threads.append(thread)
        self.active_workers.append(worker)
        thread.start()

    def handle_background_error(self, message: str) -> None:
        if hasattr(self, "home_loading"):
            self.home_loading.setText("")
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Using stored data")
        logger.error(f"Background worker error: {message}")

    def shutdown_workers(self) -> None:
        for thread in list(self.active_threads):
            thread.quit()
            thread.wait(1500)

    def build_home(self) -> None:
        page = QWidget()
        page.setStyleSheet(
            f"""
            QWidget {{
                background: {PALETTE['background']};
                color: {PALETTE['text']};
                font-family: "SF Pro Text", "Helvetica Neue";
            }}
            QLabel#HomeTitle {{
                font-family: "SF Pro Display", "Helvetica Neue";
                font-size: 32px;
                font-weight: 700;
                color: {PALETTE['text']};
            }}
            QLabel#HomeSubtitle {{
                font-family: "SF Pro Text", "Helvetica Neue";
                font-size: 16px;
                color: {PALETTE['muted']};
            }}
            QLabel#HomeSection {{
                font-family: "SF Pro Display", "Helvetica Neue";
                font-size: 22px;
                font-weight: 600;
                color: {PALETTE['text']};
            }}
            QFrame#HomeCard {{
                background: {PALETTE['panel']};
                border: 1px solid {PALETTE['border']};
                border-radius: 12px;
            }}
            QLineEdit#CitySearch {{
                background: #FFFFFF;
                border: 1px solid {PALETTE['border']};
                border-radius: 12px;
                padding: 12px 18px;
                color: {PALETTE['text']};
                font-size: 18px;
                font-family: "SF Pro Text", "Helvetica Neue";
            }}
            QPushButton#OpenDashboard {{
                background: {PALETTE['accent']};
                color: {PALETTE['text']};
                border: 0;
                border-radius: 12px;
                padding: 14px 22px;
                font-size: 18px;
                font-weight: 600;
                font-family: "SF Pro Display", "Helvetica Neue";
            }}
            QPushButton#OpenDashboard:hover {{
                background: {PALETTE['accent_hover']};
            }}
            """
        )
        layout = QVBoxLayout(page)
        layout.setContentsMargins(54, 42, 54, 42)
        layout.setSpacing(24)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        header = QLabel("FloodGuard")
        header.setObjectName("HomeTitle")
        subtitle = QLabel("Flood Risk & Evacuation Platform")
        subtitle.setObjectName("HomeSubtitle")
        title_box.addWidget(header)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        layout.addLayout(top)

        # Center Search card
        search_wrap = QFrame()
        search_wrap.setObjectName("HomeCard")
        search_layout = QVBoxLayout(search_wrap)
        search_layout.setContentsMargins(24, 24, 24, 24)
        search_layout.setSpacing(14)
        
        search_header_row = QHBoxLayout()
        search_label = QLabel("Search city")
        search_label.setObjectName("HomeSection")
        search_header_row.addWidget(search_label)
        
        self.btn_refresh_all = QPushButton("Refresh All Data")
        self.btn_refresh_all.setStyleSheet(f"background: {PALETTE['accent']}; color: white; padding: 6px 12px; font-size: 13px; font-weight: 600; border-radius: 6px;")
        self.btn_refresh_all.setVisible(False)
        self.btn_refresh_all.clicked.connect(self.refresh_all_cached_data)
        search_header_row.addWidget(self.btn_refresh_all)
        search_header_row.addStretch()
        search_layout.addLayout(search_header_row)

        self.city_search = QLineEdit()
        self.city_search.setObjectName("CitySearch")
        self.city_search.setPlaceholderText("Type a city name")
        self.city_search.textChanged.connect(self.update_search_prompt)
        self.city_search.returnPressed.connect(self.run_city_search)
        self.home_message = QLabel("Press Enter to check city data.")
        self.home_message.setStyleSheet('font-family: "SF Pro Text"; font-size: 15px; color: #666666;')
        self.home_loading = QLabel("")
        self.home_loading.setStyleSheet('font-family: "SF Pro Text"; font-size: 14px; color: #EA580C;')
        search_layout.addWidget(self.city_search)
        search_layout.addWidget(self.home_message)
        search_layout.addWidget(self.home_loading)
        layout.addWidget(search_wrap)

        self.open_dashboard_button = QPushButton("Open Dashboard")
        self.open_dashboard_button.setObjectName("OpenDashboard")
        self.open_dashboard_button.clicked.connect(self.open_dashboard)
        layout.addWidget(self.open_dashboard_button)

        # Local Database Overview Panel
        db_overview_wrap = QFrame()
        db_overview_wrap.setObjectName("HomeCard")
        db_overview_layout = QVBoxLayout(db_overview_wrap)
        db_overview_layout.setContentsMargins(24, 24, 24, 24)
        db_overview_layout.setSpacing(14)
        
        db_title_row = QHBoxLayout()
        db_section_label = QLabel("Local Database Overview")
        db_section_label.setStyleSheet("font-family: 'SF Pro Display', 'Helvetica Neue'; font-size: 22px; font-weight: 600;")
        db_title_row.addWidget(db_section_label)
        
        self.btn_view_all_cities = QPushButton("View All Cities")
        self.btn_view_all_cities.setStyleSheet(f"background: {PALETTE['accent']}; color: white; padding: 6px 12px; font-size: 13px; font-weight: 600; border-radius: 6px;")
        self.btn_view_all_cities.clicked.connect(self.open_database_manager)
        db_title_row.addWidget(self.btn_view_all_cities)
        db_title_row.addStretch()
        db_overview_layout.addLayout(db_title_row)
        
        db_info_layout = QHBoxLayout()
        
        db_stats_layout = QVBoxLayout()
        self.lbl_total_cached = QLabel("Cached Cities: --")
        self.lbl_total_cached.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.lbl_last_update = QLabel("Last Updated: --")
        self.lbl_last_update.setStyleSheet("font-size: 14px; color: #666666;")
        db_stats_layout.addWidget(self.lbl_total_cached)
        db_stats_layout.addWidget(self.lbl_last_update)
        db_info_layout.addLayout(db_stats_layout)
        
        db_info_layout.addSpacing(40)
        
        db_recent_layout = QVBoxLayout()
        db_recent_title = QLabel("Recently Cached:")
        db_recent_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #444444;")
        self.lbl_recent_cities = QLabel("None")
        self.lbl_recent_cities.setStyleSheet("font-size: 14px; color: #555555;")
        db_recent_layout.addWidget(db_recent_title)
        db_recent_layout.addWidget(self.lbl_recent_cities)
        db_info_layout.addLayout(db_recent_layout, 1)
        
        db_overview_layout.addLayout(db_info_layout)
        layout.addWidget(db_overview_wrap)

        # Status row below Search
        status_row = QHBoxLayout()
        status_row.setSpacing(18)
        self.database_status_card = self.home_status_card("Database Status", "Loading", PALETTE["yellow"])
        self.weather_status_card = self.home_status_card("Weather API Status", "Loading", PALETTE["yellow"])
        self.model_status_card = self.home_status_card("Risk Model Status", "Loading", PALETTE["yellow"])
        status_row.addWidget(self.database_status_card)
        status_row.addWidget(self.weather_status_card)
        status_row.addWidget(self.model_status_card)
        layout.addLayout(status_row)

        layout.addStretch()
        self.stack.addWidget(page)
        self.update_home_status_cards()

    def build_dashboard(self) -> None:
        page = QWidget()
        page.setStyleSheet(
            f"""
            QWidget {{
                background: {PALETTE['background']};
                color: {PALETTE['text']};
                font-family: "SF Pro Text", "Helvetica Neue";
            }}
            QFrame#DashboardCard {{
                background: {PALETTE['panel']};
                border: 1px solid {PALETTE['border']};
                border-radius: 18px;
            }}
            QLabel#DashboardTitle {{
                font-family: "SF Pro Display", "Helvetica Neue";
                font-size: 32px;
                font-weight: 750;
                color: {PALETTE['text']};
            }}
            QLabel#DashboardMeta {{
                font-size: 15px;
                color: {PALETTE['muted']};
            }}
            QLabel#KpiTitle {{
                font-size: 15px;
                color: {PALETTE['muted']};
                font-weight: 650;
            }}
            QLabel#KpiValue {{
                font-family: "SF Pro Display", "Helvetica Neue";
                font-size: 34px;
                font-weight: 800;
                color: {PALETTE['accent']};
            }}
            QSlider::groove:horizontal {{
                height: 7px;
                background: {PALETTE['border']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {PALETTE['accent']};
                width: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }}
            """
        )
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(18)

        top_bar = QHBoxLayout()
        title_block = QVBoxLayout()
        self.dashboard_city_label = QLabel("City")
        self.dashboard_city_label.setObjectName("DashboardTitle")
        self.dashboard_update_label = QLabel("Last data update: pending")
        self.dashboard_update_label.setObjectName("DashboardMeta")
        title_block.addWidget(self.dashboard_city_label)
        title_block.addWidget(self.dashboard_update_label)
        top_bar.addLayout(title_block, 1)
        self.dashboard_mode_label = QLabel("Offline")
        self.dashboard_mode_label.setObjectName("DashboardMeta")
        self.dashboard_mode_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.dashboard_status = QLabel("")
        self.dashboard_status.setObjectName("DashboardMeta")
        self.dashboard_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_bar.addWidget(self.dashboard_mode_label)
        top_bar.addWidget(self.dashboard_status)
        layout.addLayout(top_bar)

        self.dashboard_alert_banner = ClickableLabel("")
        self.dashboard_alert_banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dashboard_alert_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dashboard_alert_banner.setStyleSheet(f"background: {PALETTE['green']}; color: #FFFFFF; font-family: 'SF Pro Display', 'Helvetica Neue'; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px;")
        self.dashboard_alert_banner.setVisible(False)
        self.dashboard_alert_banner.clicked.connect(self.show_alert_details_dialog)
        layout.addWidget(self.dashboard_alert_banner)

        main = QHBoxLayout()
        main.setSpacing(18)
        map_card = QFrame()
        map_card.setObjectName("DashboardCard")
        map_layout = QVBoxLayout(map_card)
        map_layout.setContentsMargins(18, 18, 18, 18)
        map_layout.setSpacing(10)
        self.dashboard_map_view = QWebEngineView()
        self.dashboard_map_view.setPage(QuietWebEnginePage(self.dashboard_map_view))
        map_layout.addWidget(self.dashboard_map_view, 1)
        main.addWidget(map_card, 65)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(14)
        
        # Current Conditions Card
        current_card = QFrame()
        current_card.setObjectName("DashboardCard")
        current_layout = QVBoxLayout(current_card)
        current_layout.setContentsMargins(16, 14, 16, 14)
        current_layout.setSpacing(10)
        current_title = QLabel("Current Conditions")
        current_title.setObjectName("KpiTitle")
        current_layout.addWidget(current_title)
        
        self.real_rain_label = QLabel("-")
        self.real_river_label = QLabel("-")
        self.temp_label = QLabel("-")
        self.humidity_label = QLabel("-")
        self.wind_speed_label = QLabel("-")
        
        def add_kpi_row(layout_obj, label_text, val_lbl):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("DashboardMeta")
            val_lbl.setObjectName("DashboardMeta")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            row.addWidget(val_lbl)
            layout_obj.addLayout(row)
            
        add_kpi_row(current_layout, "Rainfall", self.real_rain_label)
        add_kpi_row(current_layout, "River Level", self.real_river_label)
        add_kpi_row(current_layout, "Temperature", self.temp_label)
        add_kpi_row(current_layout, "Humidity", self.humidity_label)
        add_kpi_row(current_layout, "Wind Speed", self.wind_speed_label)
        
        right_panel.addWidget(current_card)
        
        # Predicted Impact Card
        impact_card = QFrame()
        impact_card.setObjectName("DashboardCard")
        impact_layout = QVBoxLayout(impact_card)
        impact_layout.setContentsMargins(16, 14, 16, 14)
        impact_layout.setSpacing(8)
        impact_title = QLabel("Predicted Impact")
        impact_title.setObjectName("KpiTitle")
        impact_layout.addWidget(impact_title)
        
        self.score_label = QLabel("0")
        self.score_label.setObjectName("KpiValue")
        self.score_label.setStyleSheet('font-family: "SF Mono", "Menlo"; font-size: 72px; font-weight: bold;')
        self.alert_badge = QLabel("Green")
        self.alert_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.highest_zone_label = QLabel("-")
        self.highest_zone_label.setObjectName("KpiValue")
        self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold;')
        self.affected_pop_label = QLabel("-")
        self.affected_pop_label.setObjectName("KpiValue")
        self.affected_pop_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold;')
        
        def add_impact_item(layout_obj, label_text, val_lbl):
            lbl = QLabel(label_text)
            lbl.setObjectName("KpiTitle")
            layout_obj.addWidget(lbl)
            layout_obj.addWidget(val_lbl)
            
        add_impact_item(impact_layout, "Predicted Risk Score", self.score_label)
        add_impact_item(impact_layout, "Alert Level", self.alert_badge)
        add_impact_item(impact_layout, "Highest Risk Zone", self.highest_zone_label)
        add_impact_item(impact_layout, "Affected Population", self.affected_pop_label)
        
        right_panel.addWidget(impact_card)
        
        main.addLayout(right_panel, 35)
        layout.addLayout(main, 1)
 
        # Scenario Controls Card
        control_card = QFrame()
        control_card.setObjectName("DashboardCard")
        control_layout = QGridLayout(control_card)
        control_layout.setContentsMargins(18, 18, 18, 18)
        control_layout.setSpacing(12)
        control_title = QLabel("Scenario Controls")
        control_title.setObjectName("KpiTitle")
        
        self.rainfall_slider = QSlider(Qt.Orientation.Horizontal)
        self.rainfall_slider.setRange(-100, 200)
        self.river_slider = QSlider(Qt.Orientation.Horizontal)
        self.river_slider.setRange(-100, 200)
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(-100, 200)
        self.humidity_slider = QSlider(Qt.Orientation.Horizontal)
        self.humidity_slider.setRange(-100, 200)
        self.wind_slider = QSlider(Qt.Orientation.Horizontal)
        self.wind_slider.setRange(-100, 200)
        
        self.rainfall_value = QLabel("0%")
        self.river_value = QLabel("0%")
        self.temp_value = QLabel("0%")
        self.humidity_value = QLabel("0%")
        self.wind_value = QLabel("0%")
        
        for slider in [self.rainfall_slider, self.river_slider, self.temp_slider, self.humidity_slider, self.wind_slider]:
            slider.valueChanged.connect(self.update_from_sliders)
            
        rain_label = QLabel("Rainfall Scenario")
        river_label = QLabel("River Level Scenario")
        temp_label_slider = QLabel("Temperature Scenario")
        humidity_label_slider = QLabel("Humidity Scenario")
        wind_label_slider = QLabel("Wind Speed Scenario")
        
        self.reset_scenario_btn = QPushButton("Reset Scenario")
        self.reset_scenario_btn.clicked.connect(self.reset_scenario)
        self.reset_scenario_btn.setStyleSheet(f"QPushButton {{ background-color: {PALETTE['accent']}; color: #FFFFFF; font-weight: bold; padding: 8px 14px; border-radius: 6px; }} QPushButton:hover {{ background-color: {PALETTE['accent_hover']}; }}")
        
        for label in [rain_label, river_label, temp_label_slider, humidity_label_slider, wind_label_slider,
                      self.rainfall_value, self.river_value, self.temp_value, self.humidity_value, self.wind_value]:
            label.setObjectName("DashboardMeta")
            
        control_layout.addWidget(control_title, 0, 0, 1, 7)
        
        # Row 1: Rainfall & River Level
        control_layout.addWidget(rain_label, 1, 0)
        control_layout.addWidget(self.rainfall_slider, 1, 1)
        control_layout.addWidget(self.rainfall_value, 1, 2)
        
        control_layout.addWidget(river_label, 1, 3)
        control_layout.addWidget(self.river_slider, 1, 4)
        control_layout.addWidget(self.river_value, 1, 5)
        
        # Row 2: Temperature & Humidity
        control_layout.addWidget(temp_label_slider, 2, 0)
        control_layout.addWidget(self.temp_slider, 2, 1)
        control_layout.addWidget(self.temp_value, 2, 2)
        
        control_layout.addWidget(humidity_label_slider, 2, 3)
        control_layout.addWidget(self.humidity_slider, 2, 4)
        control_layout.addWidget(self.humidity_value, 2, 5)
        
        # Row 3: Wind Speed & Reset Button
        control_layout.addWidget(wind_label_slider, 3, 0)
        control_layout.addWidget(self.wind_slider, 3, 1)
        control_layout.addWidget(self.wind_value, 3, 2)
        
        control_layout.addWidget(self.reset_scenario_btn, 3, 6)
        
        layout.addWidget(control_card)
        self.stack.addWidget(page)

    def dashboard_kpi_card(self, title: str, value_widget: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DashboardCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("KpiTitle")
        value_widget.setObjectName(value_widget.objectName() or "KpiValue")
        value_widget.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_widget, 1)
        return frame

    def build_map(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(20)
        
        self.map_view = QWebEngineView()
        self.map_view.setPage(QuietWebEnginePage(self.map_view, click_handler=self.handle_map_click))
        layout.addWidget(self.map_view, 3)
        
        side_card, side_layout = card("GIS Layer Control")
        side_card.setMinimumWidth(300)
        
        self.layer_population = QCheckBox("Population Density")
        self.layer_risk = QCheckBox("Flood Risk")
        self.layer_elevation = QCheckBox("Elevation")
        self.layer_history = QCheckBox("Historical Flood Extent")
        self.layer_infra = QCheckBox("Critical Infrastructure")
        self.layer_evac = QCheckBox("Evacuation Points")
        
        checkboxes = [
            self.layer_population,
            self.layer_risk,
            self.layer_elevation,
            self.layer_history,
            self.layer_infra,
            self.layer_evac
        ]
        
        for cb in checkboxes:
            # Set default active layers
            cb.setChecked(cb in [self.layer_population, self.layer_risk, self.layer_infra, self.layer_evac])
            cb.stateChanged.connect(self.redraw_map)
            side_layout.addWidget(cb)
            
        side_layout.addSpacing(15)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"background-color: {PALETTE['border']}; max-height: 1px; border: 0;")
        side_layout.addWidget(sep)
        
        side_layout.addSpacing(10)
        
        # Zone details side panel
        zone_title_label = QLabel("Zone Information")
        zone_title_label.setStyleSheet("font-family: 'SF Pro Display'; font-size: 16px; font-weight: bold;")
        side_layout.addWidget(zone_title_label)
        
        self.lbl_map_zone_name = QLabel("Zone Name: --")
        self.lbl_map_zone_risk = QLabel("Risk Score: --")
        self.lbl_map_zone_category = QLabel("Risk Category: --")
        self.lbl_map_zone_pop = QLabel("Population: --")
        self.lbl_map_zone_elev = QLabel("Elevation: --")
        self.lbl_map_zone_river_dist = QLabel("Distance to River: --")
        self.lbl_map_zone_hist = QLabel("Hist. Flood Events: --")
        self.lbl_map_zone_shelter = QLabel("Nearest Shelter: --")
        self.lbl_map_zone_hospital = QLabel("Nearest Hospital: --")
        self.lbl_map_zone_evac = QLabel("Nearest Evacuation Point: --")
        
        self.lbl_map_zone_driver = QLabel("Select a zone or click on the map to view details.")
        self.lbl_map_zone_driver.setWordWrap(True)
        self.lbl_map_zone_driver.setStyleSheet("color: #4B5563; font-size: 13px; line-height: 1.4;")
        
        self.lbl_map_zone_reco = QLabel("Select a zone or click on the map to view details.")
        self.lbl_map_zone_reco.setWordWrap(True)
        self.lbl_map_zone_reco.setStyleSheet("color: #666666; font-size: 13px; line-height: 1.4;")
        
        for lbl in [self.lbl_map_zone_name, self.lbl_map_zone_risk, self.lbl_map_zone_category, 
                    self.lbl_map_zone_pop, self.lbl_map_zone_elev, self.lbl_map_zone_river_dist,
                    self.lbl_map_zone_hist, self.lbl_map_zone_shelter, self.lbl_map_zone_hospital,
                    self.lbl_map_zone_evac]:
            lbl.setStyleSheet("font-size: 13px;")
            side_layout.addWidget(lbl)
            
        side_layout.addSpacing(6)
        driver_lbl = QLabel("Risk Driver Explanation:")
        driver_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        side_layout.addWidget(driver_lbl)
        side_layout.addWidget(self.lbl_map_zone_driver)
        
        side_layout.addSpacing(6)
        reco_lbl = QLabel("Recommendation:")
        reco_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        side_layout.addWidget(reco_lbl)
        side_layout.addWidget(self.lbl_map_zone_reco)
        
        side_layout.addStretch()
        layout.addWidget(side_card, 1)
        self.stack.addWidget(page)

    def handle_map_click(self, lat: float, lng: float) -> None:
        if not self.current_zones:
            return
            
        def distance(lat1, lon1, lat2, lon2):
            return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5
            
        def get_dist_km(lat1, lon1, lat2, lon2):
            return (((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5) * 111.32
            
        nearest_zone = min(
            self.current_zones,
            key=lambda z: distance(lat, lng, float(z["latitude"]), float(z["longitude"]))
        )
        
        # Calculate dynamic model features
        river_dist_km = 0.0
        elevation_val = 15.0
        hist_events = 0
        if self.current_model:
            river_dist_km = self.current_model.get_river_distance(lat, lng) * 111.32
            elevation_val = self.current_model.get_elevation(lat, lng)
            hist_events = int(self.current_model.get_historical_flood_frequency(lat, lng) * 10)
        else:
            river_dist_km = get_dist_km(lat, lng, float(nearest_zone["latitude"]), float(nearest_zone["longitude"]))
            elevation_val = float(nearest_zone["elevation_m"])
            hist_events = int(float(nearest_zone.get("historical_flood_frequency") or 0.0) * 10)
            
        # Nearest Evacuation Point (any shelter)
        nearest_evac_pt = "None available"
        if self.current_shelters:
            evac = min(
                self.current_shelters,
                key=lambda s: get_dist_km(lat, lng, float(s["latitude"]), float(s["longitude"]))
            )
            nearest_evac_pt = evac["name"]
            
        # Nearest Hospital
        nearest_hosp_pt = "None available"
        hospitals = [x for x in self.current_infra if x["type"] == "hospital"]
        if hospitals:
            hosp = min(
                hospitals,
                key=lambda h: get_dist_km(lat, lng, float(h["latitude"]), float(h["longitude"]))
            )
            nearest_hosp_pt = hosp["name"]
            
        # Nearest Shelter
        nearest_shelter_pt = "None available"
        shelters_only = [x for x in self.current_shelters if "shelter" in x["name"].lower() or "centre" in x["name"].lower()]
        if not shelters_only:
            shelters_only = self.current_shelters
        if shelters_only:
            sh = min(
                shelters_only,
                key=lambda s: get_dist_km(lat, lng, float(s["latitude"]), float(s["longitude"]))
            )
            nearest_shelter_pt = sh["name"]
            
        # Calculate dynamic risk score based on model
        if self.current_model:
            score = self.current_model.get_flood_risk(lat, lng, self.scenario_rainfall, self.scenario_river_level)
        else:
            score = self.zone_scores.get(int(nearest_zone["zone_id"]), 0.0)
            
        if score >= 90.0:
            category = "Critical Alert"
            color = PALETTE["red"]
            driver = "Critical risk driven by combined low elevation basin and immediate proximity to flooding river channel."
            reco = "Immediate evacuation recommended! Secure life support assets and route to highest ground."
        elif score >= 70.0:
            category = "High Alert"
            color = PALETTE["orange"]
            driver = "High risk driven by moderate elevation vulnerability and rising local river flow volumes."
            reco = "Prepare evacuation operations. Monitor water level indicators closely and move assets to safe storage."
        elif score >= 50.0:
            category = "Moderate Alert"
            color = PALETTE["yellow"]
            driver = "Moderate risk driven by heavy localized rainfall accumulation in medium-lying urban sectors."
            reco = "Prepare emergency resources. Secure power generators and stand by for EOC instructions."
        else:
            category = "Low Alert"
            color = PALETTE["green"]
            driver = "Low risk sector with high topography and safe clearance from main drainage paths."
            reco = "No immediate actions required. Continue routine weather updates monitoring."
            
        self.lbl_map_zone_name.setText(f"<b>Zone Name:</b> {nearest_zone['name']}")
        self.lbl_map_zone_risk.setText(f"<b>Risk Score:</b> <font color='{color}'>{score:.1f} / 100</font>")
        self.lbl_map_zone_category.setText(f"<b>Risk Category:</b> <font color='{color}'>{category}</font>")
        self.lbl_map_zone_pop.setText(f"<b>Population:</b> {int(nearest_zone['population']):,}")
        self.lbl_map_zone_elev.setText(f"<b>Elevation:</b> {int(elevation_val)} m")
        self.lbl_map_zone_river_dist.setText(f"<b>Distance to River:</b> {river_dist_km:.2f} km")
        self.lbl_map_zone_hist.setText(f"<b>Hist. Flood Events:</b> {hist_events}")
        self.lbl_map_zone_shelter.setText(f"<b>Nearest Shelter:</b> {nearest_shelter_pt}")
        self.lbl_map_zone_hospital.setText(f"<b>Nearest Hospital:</b> {nearest_hosp_pt}")
        self.lbl_map_zone_evac.setText(f"<b>Nearest Evacuation Point:</b> {nearest_evac_pt}")
        
        self.lbl_map_zone_driver.setText(driver)
        self.lbl_map_zone_reco.setText(reco)
        self.lbl_map_zone_reco.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600; line-height: 1.4;")

    def evac_summary_card(self, title: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-family: 'SF Pro Text'; font-size: 13px; color: {PALETTE['muted']}; font-weight: 500;")
        value_label = QLabel("0")
        value_label.setStyleSheet(f"font-family: 'SF Mono', 'Menlo'; font-size: 32px; font-weight: bold; color: {PALETTE['accent']};")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, value_label

    def build_evacuation(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)
        
        # Summary Row at the top
        summary_row = QHBoxLayout()
        summary_row.setSpacing(16)
        
        teams_card, self.evac_teams_label = self.evac_summary_card("Teams Required")
        boats_card, self.evac_boats_label = self.evac_summary_card("Boats Required")
        zones_card, self.evac_critical_zones_label = self.evac_summary_card("Critical Risk Zones")
        
        summary_row.addWidget(teams_card)
        summary_row.addWidget(boats_card)
        summary_row.addWidget(zones_card)
        layout.addLayout(summary_row)
        
        # Grid area below summary
        grid = QGridLayout()
        grid.setSpacing(16)
        
        plan_card, plan_layout = card("Highest Priority Zones")
        self.priority_table = QTableWidget(0, 7)
        self.priority_table.setHorizontalHeaderLabels(["Area", "Risk Score", "Nearest Shelter", "Distance", "Priority", "Teams Required", "Boats Required"])
        plan_layout.addWidget(self.priority_table, 1)
        
        route_card, route_layout = card("Safe Routes View")
        self.route_view = QWebEngineView()
        self.route_view.setPage(QuietWebEnginePage(self.route_view))
        route_layout.addWidget(self.route_view, 1)
        
        select_layout = QHBoxLayout()
        select_label = QLabel("Highlight route for:")
        select_label.setObjectName("DashboardMeta")
        self.route_select_combo = QComboBox()
        self.route_select_combo.currentTextChanged.connect(lambda: self.redraw_routes(self.planner.plan(self.zone_scores) if self.planner else []))
        select_layout.addWidget(select_label)
        select_layout.addWidget(self.route_select_combo, 1)
        route_layout.addLayout(select_layout)
        
        grid.addWidget(plan_card, 0, 0)
        grid.addWidget(route_card, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid, 1)
        
        self.stack.addWidget(page)

    def build_trends(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)
        
        grid = QGridLayout()
        grid.setSpacing(18)
        
        self.canvas_rain = MplCanvas()
        self.canvas_river = MplCanvas()
        self.canvas_risk = MplCanvas()
        self.canvas_temp = MplCanvas()
        self.canvas_pop = MplCanvas()
        self.canvas_alert = MplCanvas()
        
        def make_card(title, canvas):
            c, l = card(title)
            l.addWidget(canvas)
            return c
            
        grid.addWidget(make_card("Rainfall History", self.canvas_rain), 0, 0)
        grid.addWidget(make_card("River Level History", self.canvas_river), 0, 1)
        grid.addWidget(make_card("Flood Risk Trend", self.canvas_risk), 1, 0)
        grid.addWidget(make_card("Temperature & Humidity Trend", self.canvas_temp), 1, 1)
        grid.addWidget(make_card("Population At Risk", self.canvas_pop), 2, 0)
        grid.addWidget(make_card("Alert Level Timeline", self.canvas_alert), 2, 1)
        
        layout.addLayout(grid)
        self.stack.addWidget(page)

    def build_advisor(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)
        
        # Left card for assistant chat
        chat_card, chat_layout = card("FloodGuard AI Advisor")
        
        # Header layout (Status + Action buttons)
        header_layout = QHBoxLayout()
        self.ai_status = QLabel("Checking connection...")
        self.ai_status.setStyleSheet(f"font-size: 13px; color: {PALETTE['muted']}; font-weight: 500;")
        
        self.btn_install_model = QPushButton("Install Model")
        self.btn_install_model.clicked.connect(self.pull_ollama_model)
        self.btn_install_model.setStyleSheet(f"QPushButton {{ background-color: {PALETTE['accent']}; color: #FFFFFF; font-weight: bold; padding: 6px 12px; border-radius: 6px; }}")
        self.btn_install_model.hide()
        
        header_layout.addWidget(self.ai_status)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_install_model)
        
        self.ai_chat = QTextBrowser()
        self.ai_chat.setOpenExternalLinks(True)
        self.ai_chat.setStyleSheet(f"background: {PALETTE['surface']}; border: 1px solid {PALETTE['border']}; font-family: 'SF Pro Text'; font-size: 14px; padding: 12px; border-radius: 8px;")
        
        # Bottom tool row
        tool_row = QHBoxLayout()
        self.btn_clear_chat = QPushButton("Clear Conversation")
        self.btn_clear_chat.clicked.connect(self.clear_chat)
        self.btn_copy_chat = QPushButton("Copy Response")
        self.btn_copy_chat.clicked.connect(self.copy_chat)
        for b in [self.btn_clear_chat, self.btn_copy_chat]:
            b.setStyleSheet(f"QPushButton {{ background-color: transparent; border: 1px solid {PALETTE['border']}; color: {PALETTE['text']}; padding: 6px 12px; border-radius: 6px; }} QPushButton:hover {{ background-color: {PALETTE['panel']}; }}")
        tool_row.addWidget(self.btn_clear_chat)
        tool_row.addStretch()
        tool_row.addWidget(self.btn_copy_chat)
        
        input_row = QHBoxLayout()
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText("Query the FloodGuard Operations Assistant...")
        self.ai_input.setStyleSheet("font-size: 14px; padding: 12px; border-radius: 8px;")
        self.ai_input.returnPressed.connect(self.ask_ai)
        
        self.ai_send = QPushButton("Send")
        self.ai_send.clicked.connect(self.ask_ai)
        self.ai_send.setStyleSheet(f"QPushButton {{ background-color: {PALETTE['accent']}; color: #FFFFFF; font-weight: bold; padding: 12px 24px; border-radius: 8px; }} QPushButton:hover {{ background-color: {PALETTE['accent_hover']}; }}")
        
        input_row.addWidget(self.ai_input, 1)
        input_row.addWidget(self.ai_send)
        
        chat_layout.addLayout(header_layout)
        chat_layout.addWidget(self.ai_chat, 1)
        chat_layout.addLayout(tool_row)
        chat_layout.addLayout(input_row)
        
        # Right card for Quick Actions
        presets_card, presets_layout = card("Quick Actions")
        presets_layout.setSpacing(12)
        
        info_lbl = QLabel("Generate operational briefings using live dashboard context:")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 13px; line-height: 1.4;")
        presets_layout.addWidget(info_lbl)
        
        actions = [
            ("Analyze Current Situation", "actions"),
            ("Explain Flood Risk", "risk"),
            ("Generate Public Warning", "warning"),
            ("Generate Evacuation Plan", "evac"),
            ("Generate Resource Deployment Plan", "resource"),
            ("Generate Situation Report", "sitrep")
        ]
        
        for label, tag in actions:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, t=tag: self.ask_ai_preset(t))
            btn.setStyleSheet(f"QPushButton {{ background-color: {PALETTE['panel']}; border: 1px solid {PALETTE['border']}; color: {PALETTE['text']}; text-align: left; padding: 12px 14px; font-weight: 600; font-size: 14px; border-radius: 8px; }} QPushButton:hover {{ background-color: {PALETTE['surface']}; }}")
            presets_layout.addWidget(btn)
            
        presets_layout.addStretch()
        
        layout.addWidget(chat_card, 5)
        layout.addWidget(presets_card, 2)
        self.stack.addWidget(page)
        self.check_ollama()

    def clear_chat(self) -> None:
        self.ai_messages = []
        self.ai_chat.clear()

    def copy_chat(self) -> None:
        QApplication.clipboard().setText(self.ai_chat.toPlainText())

    def append_chat_bubble(self, sender: str, message: str, is_user: bool) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        bg_color = PALETTE["panel"] if is_user else PALETTE["surface"]
        align = "right" if is_user else "left"
        border = f"1px solid {PALETTE['border']}"
        margin = "margin-left: 20%;" if is_user else "margin-right: 20%;"
        
        html = f'''
        <div align="{align}">
            <div style="background-color: {bg_color}; border: {border}; border-radius: 8px; padding: 10px; {margin} margin-bottom: 10px; display: inline-block; text-align: left;">
                <div style="font-weight: bold; color: {PALETTE['accent']};">{sender}</div>
                <div style="margin-top: 6px; margin-bottom: 6px; white-space: pre-wrap; font-size: 14px;">{message}</div>
                <div style="font-size: 11px; color: {PALETTE['muted']}; text-align: right;">{timestamp}</div>
            </div>
        </div>
        '''
        self.ai_chat.append(html)

    def ask_ai_preset(self, preset_type: str) -> None:
        prompts = {
            "actions": "Analyze the current situation. Output the current risk level, most affected zone, people at risk, primary causes, and recommended immediate actions.",
            "risk": "Explain the flood risk. Provide the risk score, why the score is high, contributing factors, risk trend, and future concerns.",
            "warning": "Generate a public warning. Provide an official warning message in simple language, public safe actions, and emergency numbers placeholders.",
            "evac": "Generate an evacuation plan. Detail the zones to evacuate first, nearest shelters, priority ranking, and suggested route strategy.",
            "resource": "Generate a resource deployment plan. Outline rescue teams needed, boats needed, medical units needed, and high priority locations.",
            "sitrep": "Generate a Situation Report formatted as: FLOODGUARD SITUATION REPORT, City, Date & Time, Risk Score, Alert Level, Affected Zones, Critical Infrastructure Status, Shelter Status, Resource Requirements, Recommendations."
        }
        prompt = prompts.get(preset_type, "")
        if not prompt:
            return
        self.ai_input.setText(prompt)
        self.ask_ai()

    def toggle_online(self) -> None:
        self.online_mode = self.mode_toggle.isChecked()
        self.mode_toggle.setText("Online Mode" if self.online_mode else "Offline Mode")
        self.city_search.setPlaceholderText("Search local cities or add a city online" if self.online_mode else "Search stored cities")
        
        if self.online_mode:
            logger.info("Online mode enabled")
            self.set_home_status(self.weather_status_card, "Fetching", PALETTE["yellow"])
            
            def check_online_status() -> dict:
                internet = check_internet()
                api = check_api_availability() if internet else False
                return {"internet": internet, "api": api}
                
            def success(res: dict) -> None:
                if res["internet"] and res["api"]:
                    self.set_home_status(self.weather_status_card, "Connected", PALETTE["green"])
                    if hasattr(self, "btn_refresh_all"):
                        self.btn_refresh_all.setVisible(True)
                else:
                    self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
                    if hasattr(self, "btn_refresh_all"):
                        self.btn_refresh_all.setVisible(False)
                    if not res["internet"]:
                        self.home_message.setText("No internet connection available.")
                        logger.error("API failure: No internet connection available.")
                    else:
                        self.home_message.setText("Unable to fetch live data. Using cached data.")
                        logger.error("API failure: Weather API is unavailable.")
                self.fetch_weather_if_online()
                
            def failed(msg: str) -> None:
                self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
                if hasattr(self, "btn_refresh_all"):
                    self.btn_refresh_all.setVisible(False)
                self.home_message.setText("Unable to fetch live data. Using cached data.")
                logger.error(f"API failure: {msg}")
                self.fetch_weather_if_online()
                
            self.run_background(check_online_status, success, failed)
        else:
            logger.info("Online mode disabled")
            self.set_home_status(self.weather_status_card, "Offline", PALETTE["muted"])
            if hasattr(self, "btn_refresh_all"):
                self.btn_refresh_all.setVisible(False)
            self.update_home_status_cards()
            self.fetch_weather_if_online()

    def load_city(self, name: str) -> None:
        if not name:
            return
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Loading city data...")

        def task() -> dict:
            bundle = self.cache_service.load_city(name)
            if not bundle:
                raise ValueError("City not found in cache")
            
            lat = bundle["city"]["latitude"]
            lon = bundle["city"]["longitude"]
            base_elev = bundle["city"].get("elevation", 15.0)
            model = CityDistributionModel(lat, lon, base_elev)
            
            osm_infra = []
            osm_shelters = []
            if self.online_mode:
                try:
                    bbox = f"{lat-0.12},{lon-0.12},{lat+0.12},{lon+0.12}"
                    url = "https://overpass-api.de/api/interpreter"
                    query = f"""
                    [out:json][timeout:5];
                    (
                      node["amenity"~"hospital|clinic|school|college|university|fire_station|police|shelter|townhall|community_centre"]({bbox});
                      way["amenity"~"hospital|clinic|school|college|university|fire_station|police|shelter|townhall|community_centre"]({bbox});
                      node["power"~"plant|substation"]({bbox});
                      node["man_made"~"water_works|wastewater_works"]({bbox});
                      node["office"="government"]({bbox});
                    );
                    out center;
                    """
                    r = requests.post(url, data={"data": query}, timeout=6.0)
                    if r.status_code == 200:
                        elements = r.json().get("elements", [])
                        for el in elements:
                            el_lat = el.get("lat") or el.get("center", {}).get("lat")
                            el_lon = el.get("lon") or el.get("center", {}).get("lon")
                            if el_lat is None or el_lon is None:
                                continue
                            tags = el.get("tags", {})
                            name_str = tags.get("name")
                            amenity = tags.get("amenity")
                            power = tags.get("power")
                            man_made = tags.get("man_made")
                            office = tags.get("office")
                            
                            # Categorize
                            el_type = None
                            if amenity in ["hospital", "clinic", "doctors"]:
                                el_type = "hospital"
                                name_str = name_str or "Emergency Hospital"
                            elif amenity in ["school", "college", "university"]:
                                el_type = "school"
                                name_str = name_str or "Community School"
                            elif amenity == "fire_station":
                                el_type = "fire_station"
                                name_str = name_str or "Local Fire Station"
                            elif amenity == "police":
                                el_type = "police"
                                name_str = name_str or "Police Station Precinct"
                            elif power in ["plant", "substation"]:
                                el_type = "power_station"
                                name_str = name_str or "Power Plant/Grid Node"
                            elif man_made in ["water_works", "wastewater_works"]:
                                el_type = "water_treatment"
                                name_str = name_str or "Water Treatment Plant"
                            elif amenity in ["townhall", "community_centre"] or office == "government":
                                el_type = "relief_center"
                                name_str = name_str or "Government Relief Office"
                            elif amenity == "shelter":
                                el_type = "shelter"
                                name_str = name_str or "Emergency Shelter Base"
                                
                            if el_type:
                                if el_type == "shelter":
                                    osm_shelters.append({
                                        "name": name_str,
                                        "latitude": float(el_lat),
                                        "longitude": float(el_lon),
                                        "capacity": 5000 + random.randint(0, 5000),
                                        "current_occupancy": 200 + random.randint(0, 800)
                                    })
                                else:
                                    osm_infra.append({
                                        "type": el_type,
                                        "name": name_str,
                                        "latitude": float(el_lat),
                                        "longitude": float(el_lon)
                                    })
                except Exception as e:
                    logger.error(f"OSM Overpass API request failed: {e}")

            # Initialize lists from OSM or DB
            infra_by_type = {}
            for t in ["hospital", "school", "fire_station", "police", "power_station", "water_treatment", "relief_center"]:
                infra_by_type[t] = [x for x in osm_infra if x["type"] == t]
                
            # Fallback to database loaded infra if OSM returned nothing
            if not any(infra_by_type.values()):
                for x in bundle["infrastructure"]:
                    t = x["type"]
                    if t in infra_by_type:
                        infra_by_type[t].append(x)
                        
            # Evacuation / Shelters list
            shelters_list = list(osm_shelters)
            if not shelters_list:
                shelters_list = list(bundle["shelters"])
                
            # Helper to generate missing points
            def generate_points(criteria_fn, count_needed):
                points = []
                lat_min, lat_max = lat - 0.08, lat + 0.08
                lon_min, lon_max = lon - 0.08, lon + 0.08
                candidates = []
                for _ in range(150):
                    clat = random.uniform(lat_min, lat_max)
                    clon = random.uniform(lon_min, lon_max)
                    score = criteria_fn(clat, clon)
                    candidates.append((clat, clon, score))
                candidates.sort(key=lambda x: x[2], reverse=True)
                for clat, clon, score in candidates:
                    if len(points) >= count_needed:
                        break
                    # diversity check
                    too_close = False
                    for plat, plon in points:
                        if ((clat - plat)**2 + (clon - plon)**2)**0.5 < 0.012:
                            too_close = True
                            break
                    if not too_close:
                        points.append((clat, clon))
                for clat, clon, score in candidates:
                    if len(points) >= count_needed:
                        break
                    points.append((clat, clon))
                return points

            # Generate missing infrastructure
            min_counts = {
                "hospital": 10,
                "school": 10,
                "fire_station": 5,
                "police": 5,
                "power_station": 5,
                "water_treatment": 5,
                "relief_center": 5
            }
            
            criterias = {
                "hospital": lambda lt, ln: model.get_population_density(lt, ln),
                "school": lambda lt, ln: model.get_population_density(lt, ln),
                "fire_station": lambda lt, ln: model.get_population_density(lt, ln),
                "police": lambda lt, ln: model.get_population_density(lt, ln),
                "power_station": lambda lt, ln: model.get_population_density(lt, ln) * (1.0 - math.exp(-model.get_river_distance(lt, ln)**2 / 0.002)) * (1.0 - model.get_population_density(lt, ln)),
                "water_treatment": lambda lt, ln: math.exp(-model.get_river_distance(lt, ln)**2 / 0.0005),
                "relief_center": lambda lt, ln: model.get_population_density(lt, ln)
            }
            
            names_templates = {
                "hospital": ["General Hospital", "City Clinic", "Health Pavilion", "Medicare Hospital", "Red Cross Hospital", "St. Jude Hospital", "Mercy Health", "Apex Hospital", "Unity Clinic", "Central Hospital"],
                "school": ["High School", "Academy", "Public School", "Memorial High", "St. Xavier's", "Grammar School", "Science Academy", "Valley School", "Riverdale High", "Central School"],
                "fire_station": ["Fire HQ", "Station 1", "Fire Station 2", "Station 3", "Emergency Response 4"],
                "police": ["Precinct 1", "Precinct 2", "Police Station", "City Jail Node", "Police HQ"],
                "power_station": ["Power Substation A", "Substation B", "Grid Center C", "Electric Hub D", "Power Generator E"],
                "water_treatment": ["Water Treatment Facility", "Water Reclamation Center", "Reservoir Plant A", "Filtration Hub B", "Pump Station C"],
                "relief_center": ["Community Relief Hub", "Town Hall Office", "Civil Relief Center", "Government Helpdesk", "Red Cross Aid Station"]
            }

            final_infra = []
            infra_id_counter = 1
            
            for t, min_cnt in min_counts.items():
                existing = infra_by_type[t]
                final_infra.extend(existing)
                
                needed = min_cnt - len(existing)
                if needed > 0:
                    generated = generate_points(criterias[t], needed)
                    for idx, (plat, plon) in enumerate(generated):
                        name_str = f"{name} {names_templates[t][idx % len(names_templates[t])]}"
                        final_infra.append({
                            "infra_id": bundle["city"]["city_id"] * 1000 + infra_id_counter,
                            "city_id": bundle["city"]["city_id"],
                            "zone_id": bundle["zones"][idx % len(bundle["zones"])]["zone_id"] if bundle["zones"] else 0,
                            "type": t,
                            "name": name_str,
                            "latitude": round(plat, 5),
                            "longitude": round(plon, 5)
                        })
                        infra_id_counter += 1

            # Generate missing evacuation points (minimum 15!)
            needed_shelters = 15 - len(shelters_list)
            if needed_shelters > 0:
                shelter_criteria = lambda lt, ln: model.get_elevation(lt, ln) * (1.0 - model.get_population_density(lt, ln))
                generated_shelters = generate_points(shelter_criteria, needed_shelters)
                shelter_templates = ["Municipal Shelter", "Sports Complex Camp", "Stadium Relief Site", "College Hall Shelter", "Transit Hub Shelter", "Community Hall A", "NGO Relief Camp", "Primary School Shelter", "Sector 4 Camp", "Central Shelter Site"]
                for idx, (plat, plon) in enumerate(generated_shelters):
                    name_str = f"{name} {shelter_templates[idx % len(shelter_templates)]}"
                    shelters_list.append({
                        "shelter_id": bundle["city"]["city_id"] * 100 + len(shelters_list) + 1,
                        "city_id": bundle["city"]["city_id"],
                        "name": name_str,
                        "latitude": round(plat, 5),
                        "longitude": round(plon, 5),
                        "capacity": 3000 + random.randint(0, 3000),
                        "current_occupancy": 100 + random.randint(0, 900)
                    })
                    
            # Generate Historical Flood Points (15 points)
            flood_criteria = lambda lt, ln: model.get_historical_flood_frequency(lt, ln)
            generated_flood_pts = generate_points(flood_criteria, 15)
            flood_points = []
            for idx, (plat, plon) in enumerate(generated_flood_pts):
                flood_points.append({
                    "name": f"Historical Flood Zone Sector {idx + 1}",
                    "latitude": round(plat, 5),
                    "longitude": round(plon, 5),
                    "frequency": round(0.4 + random.random() * 0.8, 2)
                })

            bundle["infrastructure"] = final_infra
            bundle["shelters"] = shelters_list
            bundle["historical_flood_points"] = flood_points
            return bundle

        self.run_background(task, self.apply_city_data)

    def apply_city_data(self, payload: dict) -> None:
        self.current_city = payload["city"]
        self.current_zones = payload["zones"]
        self.current_shelters = payload["shelters"]
        self.current_infra = payload["infrastructure"]
        self.current_history = payload["history"]
        self.current_historical_flood_points = payload.get("historical_flood_points", [])
        
        # Initialize CityDistributionModel
        self.current_model = CityDistributionModel(
            self.current_city["latitude"], 
            self.current_city["longitude"], 
            self.current_city.get("elevation", 15.0)
        )
        
        self.planner = EvacuationPlanner(self.current_zones, self.current_shelters)
        self.dashboard_city_label.setText(self.current_city["name"])
        self.dashboard_mode_label.setText("Online Mode" if self.online_mode else "Offline Mode")
        self.dashboard_update_label.setText("Last data update: loading scenario")
        self.redraw_dashboard_map()
        self.set_default_sliders()
        self.fetch_weather_if_online()
        self.refresh_all()

    def refresh_city_combos(self) -> None:
        current = self.current_city["name"] if self.current_city else ""
        if hasattr(self, "compare_combo"):
            self.compare_combo.blockSignals(True)
            self.compare_combo.clear()
            self.compare_combo.addItems([city["name"] for city in self.cities_list])
            if current:
                index = self.compare_combo.findText(current)
                if index >= 0:
                    self.compare_combo.setCurrentIndex(index)
            self.compare_combo.blockSignals(False)

    def set_default_sliders(self) -> None:
        if not self.current_city:
            return
            
        self.real_temperature = float(self.current_city.get("temperature") or 0.0)
        self.real_humidity = float(self.current_city.get("humidity") or 0.0)
        self.real_wind_speed = float(self.current_city.get("wind_speed") or 0.0)
        
        if self.current_history:
            recent = self.current_history[-1]
            self.real_rainfall = float(recent.get("rainfall_mm") or 0.0)
            self.real_river_level = float(recent.get("river_level_m") or 1.5)
        else:
            self.real_rainfall = float(self.current_city.get("rainfall") or 0.0)
            self.real_river_level = 1.5
            
        self.scenario_rainfall = self.real_rainfall
        self.scenario_river_level = self.real_river_level
        self.scenario_temperature = self.real_temperature
        self.scenario_humidity = self.real_humidity
        self.scenario_wind_speed = self.real_wind_speed
        
        for slider in [self.rainfall_slider, self.river_slider, self.temp_slider, self.humidity_slider, self.wind_slider]:
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)

    def fetch_weather_if_online(self) -> None:
        self.using_cached = False
        if not self.online_mode:
            if hasattr(self, "weather_status_card"):
                self.set_home_status(self.weather_status_card, "Offline", PALETTE["muted"])
            return
        if not self.current_city:
            return
            
        if hasattr(self, "home_loading"):
            self.home_loading.setText("Updating weather...")
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Updating weather...")

        city_id = int(self.current_city["city_id"])
        lat = float(self.current_city["latitude"])
        lon = float(self.current_city["longitude"])

        def task() -> dict:
            if not check_internet():
                raise ConnectionError("No internet connection available.")
            payload = self.weather_service.fetch_weather(lat, lon)
            self.cache_service.update_city(city_id, payload)
            return payload

        def success(payload: dict) -> None:
            self.real_temperature = float(payload["temperature"])
            self.real_humidity = float(payload["humidity"])
            self.real_wind_speed = float(payload["wind_speed"])
            self.real_rainfall = float(payload["rainfall_mm"])
            
            # Keep current city metadata updated
            self.current_city["temperature"] = payload["temperature"]
            self.current_city["humidity"] = payload["humidity"]
            self.current_city["wind_speed"] = payload["wind_speed"]
            self.current_city["rainfall"] = payload["rainfall_mm"]
            
            # Sync scenario variables
            self.scenario_rainfall = self.real_rainfall
            self.scenario_river_level = self.real_river_level
            
            self.rainfall_slider.blockSignals(True)
            self.river_slider.blockSignals(True)
            self.rainfall_slider.setValue(0)
            self.river_slider.setValue(0)
            self.rainfall_slider.blockSignals(False)
            self.river_slider.blockSignals(False)
            
            self.last_data_update = datetime.now()
            
            if hasattr(self, "weather_status_card"):
                self.set_home_status(self.weather_status_card, "Connected", PALETTE["green"])
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            if hasattr(self, "dashboard_status"):
                self.dashboard_status.setText("")
            self.update_dashboard()

        def failed(message: str) -> None:
            self.using_cached = True
            if hasattr(self, "weather_status_card"):
                self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            if hasattr(self, "dashboard_status"):
                self.dashboard_status.setText("Using stored data")
            
            if "no internet" in message.lower() or "connection" in message.lower():
                self.home_message.setText("No internet connection available.")
                logger.error(f"API failure: {message}")
            else:
                self.home_message.setText("Unable to fetch live data. Using cached data.")
                logger.error(f"API failure: {message}")

        self.run_background(task, success, failed)

    def apply_db_overview(self, cities: list[dict]) -> None:
        self.cities_list = cities
        self.refresh_city_combos()
        
        if not hasattr(self, "lbl_total_cached"):
            return
            
        total = len(cities)
        self.lbl_total_cached.setText(f"Cached Cities: {total}")
        
        latest_time = None
        for c in cities:
            lu = c.get("last_updated")
            if lu:
                if isinstance(lu, str):
                    try:
                        lu_dt = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                    except Exception:
                        lu_dt = None
                else:
                    lu_dt = lu
                if lu_dt:
                    if latest_time is None or lu_dt > latest_time:
                        latest_time = lu_dt
                        
        if latest_time:
            self.lbl_last_update.setText(f"Last Updated:\n{latest_time.strftime('%d %b %Y %H:%M')}")
        else:
            self.lbl_last_update.setText("Last Updated:\n--")
            
        def sort_key(city_dict):
            lu = city_dict.get("last_updated")
            if not lu:
                return datetime.min
            if isinstance(lu, str):
                try:
                    return datetime.fromisoformat(lu.replace("Z", "+00:00"))
                except Exception:
                    return datetime.min
            return lu
            
        sorted_cities = sorted(cities, key=sort_key, reverse=True)
        recent_names = [c["name"] for c in sorted_cities[:5]]
        
        if recent_names:
            bullet_list = "\n".join([f"• {name}" for name in recent_names])
            extra = total - 5
            if extra > 0:
                bullet_list += f"\n* {extra} more cities"
            self.lbl_recent_cities.setText(bullet_list)
        else:
            self.lbl_recent_cities.setText("None")

    def update_db_overview(self) -> None:
        def task() -> list[dict]:
            return self.cache_service.get_all_cities()
        def success(cities: list[dict]) -> None:
            self.apply_db_overview(cities)
        self.run_background(task, success)

    def open_database_manager(self) -> None:
        from PyQt6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QHeaderView
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Cached Cities Database")
        dialog.setMinimumSize(700, 450)
        dialog.setStyleSheet(f"background: {PALETTE['background']}; color: {PALETTE['text']};")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        
        title = QLabel("Cached Cities Database")
        title.setStyleSheet(f"font-family: 'SF Pro Display'; font-size: 20px; font-weight: bold; color: {PALETTE['text']};")
        layout.addWidget(title)
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["City", "State", "Latitude", "Longitude", "Last Updated"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(f"background: {PALETTE['panel']}; color: {PALETTE['text']}; gridline-color: {PALETTE['border']};")
        layout.addWidget(table)
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"background: {PALETTE['border']}; color: {PALETTE['text']}; padding: 8px; border-radius: 6px;")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        def load_table():
            cities = self.cache_service.get_all_cities()
            table.setRowCount(len(cities))
            for row, city in enumerate(cities):
                table.setItem(row, 0, QTableWidgetItem(city["name"]))
                table.setItem(row, 1, QTableWidgetItem(city.get("state") or ""))
                table.setItem(row, 2, QTableWidgetItem(f"{float(city['latitude']):.4f}"))
                table.setItem(row, 3, QTableWidgetItem(f"{float(city['longitude']):.4f}"))
                
                lu = city.get("last_updated")
                if lu:
                    if isinstance(lu, datetime):
                        lu_str = lu.strftime("%d %b %Y %H:%M")
                    else:
                        lu_str = str(lu)
                else:
                    lu_str = "--"
                table.setItem(row, 4, QTableWidgetItem(lu_str))
                
        load_table()
        dialog.exec()

    def refresh_all_cached_data(self) -> None:
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton
        
        # Check if internet is available first
        self.set_home_status(self.weather_status_card, "Fetching", PALETTE["yellow"])
        if not check_internet():
            self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
            self.home_message.setText("✗ No internet connection")
            QMessageBox.warning(self, "Network Error", "No internet connection available. Cannot refresh data.")
            logger.error("Refresh failure: No internet connection available.")
            return

        # Fetch cached cities
        cities = self.cache_service.get_all_cities()
        if not cities:
            QMessageBox.information(self, "Database Empty", "No cached cities found in the database.")
            return

        # Helper to check if a city is stale
        def is_city_stale(city) -> bool:
            lu = city.get("last_updated")
            if not lu:
                return True
            if isinstance(lu, str):
                try:
                    lu = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                except Exception:
                    return True
            lu_naive = lu.replace(tzinfo=None) if lu.tzinfo else lu
            diff = datetime.now() - lu_naive
            return diff.total_seconds() > 5 * 60

        # Filter stale cities
        stale_cities = [c for c in cities if is_city_stale(c)]
        if not stale_cities:
            self.set_home_status(self.weather_status_card, "Connected", PALETTE["green"])
            QMessageBox.information(self, "Refresh Complete", "All cached cities are up to date (updated within the last 5 minutes).")
            return

        # Set status cards
        self.set_home_status(self.database_status_card, "Updating", PALETTE["yellow"])
        self.set_home_status(self.weather_status_card, "Fetching", PALETTE["yellow"])

        dialog = QDialog(self)
        dialog.setWindowTitle("Refreshing City Data")
        dialog.setMinimumSize(400, 300)
        dialog.setStyleSheet(f"background: {PALETTE['background']}; color: {PALETTE['text']};")
        
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(18, 18, 18, 18)
        dlg_layout.setSpacing(12)
        
        title_lbl = QLabel("Refreshing city data…")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; font-family: 'SF Pro Display';")
        dlg_layout.addWidget(title_lbl)
        
        progress_area = QTextEdit()
        progress_area.setReadOnly(True)
        progress_area.setStyleSheet(f"background: {PALETTE['panel']}; color: {PALETTE['text']}; border: 1px solid {PALETTE['border']}; font-family: 'SF Mono', monospace; font-size: 13px;")
        dlg_layout.addWidget(progress_area)
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"background: {PALETTE['accent']}; color: white; padding: 8px; border-radius: 6px;")
        close_btn.setEnabled(False)
        close_btn.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_btn)
        
        dialog.show()
        
        def process_city(index: int) -> None:
            if index >= len(stale_cities):
                progress_area.append("\nCompleted")
                close_btn.setEnabled(True)
                self.update_db_overview()
                self.update_home_status_cards()
                logger.info("Refresh All: Completed successfully")
                return
                
            city = stale_cities[index]
            city_name = city["name"]
            city_id = city["city_id"]
            lat = float(city["latitude"])
            lon = float(city["longitude"])
            
            progress_area.append(f"Refreshing {city_name}...")
            
            def task() -> dict:
                try:
                    weather_data = self.weather_service.fetch_weather(lat, lon)
                    self.cache_service.update_city(city_id, weather_data)
                    logger.info(f"Cache update: Successfully updated cache for city {city_name} (ID: {city_id})")
                    return {"success": True, "name": city_name}
                except Exception as e:
                    logger.error(f"Refresh failure: Failed to refresh {city_name} (ID: {city_id}): {e}")
                    return {"success": False, "name": city_name, "error": str(e)}
                    
            def success(res: dict) -> None:
                if res["success"]:
                    progress_area.append(f"{res['name']} ✓")
                else:
                    progress_area.append(f"{res['name']} ✗ ({res['error']})")
                process_city(index + 1)
                
            self.run_background(task, success)
            
        process_city(0)

    def update_from_sliders(self) -> None:
        if not self.current_zones:
            return
        rain_pct = float(self.rainfall_slider.value())
        river_pct = float(self.river_slider.value())
        temp_pct = float(self.temp_slider.value())
        humidity_pct = float(self.humidity_slider.value())
        wind_pct = float(self.wind_slider.value())
        
        if self.real_rainfall > 0.0:
            self.scenario_rainfall = max(0.0, self.real_rainfall * (1.0 + rain_pct / 100.0))
        else:
            self.scenario_rainfall = max(0.0, (rain_pct / 100.0) * 100.0) if rain_pct > 0 else 0.0
            
        if self.real_river_level > 0.0:
            self.scenario_river_level = max(0.0, self.real_river_level * (1.0 + river_pct / 100.0))
        else:
            self.scenario_river_level = max(0.0, (river_pct / 100.0) * 5.0) if river_pct > 0 else 0.0

        self.scenario_temperature = max(-10.0, self.real_temperature * (1.0 + temp_pct / 100.0))
        self.scenario_humidity = min(100.0, max(0.0, self.real_humidity * (1.0 + humidity_pct / 100.0)))
        self.scenario_wind_speed = max(0.0, self.real_wind_speed * (1.0 + wind_pct / 100.0))
            
        rain_sign = "+" if rain_pct >= 0 else ""
        river_sign = "+" if river_pct >= 0 else ""
        temp_sign = "+" if temp_pct >= 0 else ""
        hum_sign = "+" if humidity_pct >= 0 else ""
        wind_sign = "+" if wind_pct >= 0 else ""
        
        self.rainfall_value.setText(f"{self.scenario_rainfall:.1f} mm ({rain_sign}{rain_pct:.0f}%)")
        self.river_value.setText(f"{self.scenario_river_level:.1f} m ({river_sign}{river_pct:.0f}%)")
        self.temp_value.setText(f"{self.scenario_temperature:.1f} °C ({temp_sign}{temp_pct:.0f}%)")
        self.humidity_value.setText(f"{self.scenario_humidity:.0f}% ({hum_sign}{humidity_pct:.0f}%)")
        self.wind_value.setText(f"{self.scenario_wind_speed:.1f} km/h ({wind_sign}{wind_pct:.0f}%)")
        
        self.risk_request_id += 1
        request_id = self.risk_request_id
        zones = [dict(zone) for zone in self.current_zones]
        history = [dict(row) for row in self.current_history]
        city_id = int(self.current_city["city_id"])
        mode = "online" if self.online_mode and not self.using_cached else "offline"
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Updating scenario...")
        self.set_home_status(self.model_status_card, "Predicting", PALETTE["yellow"])

        def task() -> dict:
            res = self.risk_service.score_scenario(self.scenario_rainfall, self.scenario_river_level, zones, history)
            
            # Apply adjustments to zone_results and city_result based on weights:
            # Humidity (Medium weight: 0.10), Temp (Low weight: 0.035), Wind (Low weight: 0.015)
            adjustment = (humidity_pct * 0.10) + (temp_pct * 0.035) + (wind_pct * 0.015)
            
            for zone_id, zone_res in res["zone_results"].items():
                new_score = min(100.0, max(0.0, zone_res.score + adjustment))
                zone_res.score = new_score
                # Recompute low/high confidence based on new score and baseline spread
                spread = zone_res.confidence_high - zone_res.confidence_low
                zone_res.confidence_low = max(0.0, new_score - spread/2.0)
                zone_res.confidence_high = min(100.0, new_score + spread/2.0)
                
            # Recompute city score
            from floodguard.risk_model import city_score
            res["city_result"] = city_score(res["zone_results"])
            
            self.cache_service.log_simulation(
                city_id,
                self.scenario_rainfall,
                self.scenario_river_level,
                res["city_result"].score,
                res["city_result"].confidence_low,
                res["city_result"].confidence_high,
                mode,
                res["city_result"].explanation,
                alert_level(res["city_result"].score),
            )
            return {"request_id": request_id, "zone_results": res["zone_results"], "city_result": res["city_result"]}

        self.run_background(task, self.apply_risk_result)

    def reset_scenario(self) -> None:
        self.scenario_rainfall = self.real_rainfall
        self.scenario_river_level = self.real_river_level
        self.scenario_temperature = self.real_temperature
        self.scenario_humidity = self.real_humidity
        self.scenario_wind_speed = self.real_wind_speed
        
        for slider in [self.rainfall_slider, self.river_slider, self.temp_slider, self.humidity_slider, self.wind_slider]:
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            
        self.update_from_sliders()

    def apply_risk_result(self, payload: dict) -> None:
        if payload["request_id"] != self.risk_request_id:
            return
        self.zone_results = payload["zone_results"]
        self.zone_scores = {zone_id: result.score for zone_id, result in self.zone_results.items()}
        self.city_result = payload["city_result"]
        self.last_data_update = datetime.now()
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("")
        self.set_home_status(self.model_status_card, "Loaded", PALETTE["green"])
        self.update_dashboard()
        if self.stack.currentIndex() == 2:
            self.redraw_map()
        if self.stack.currentIndex() == 3:
            self.refresh_evacuation()

    def show_alert_details_dialog(self) -> None:
        dialog = AlertDetailsDialog(self)
        dialog.exec()

    def update_dashboard(self) -> None:
        if not self.current_city:
            self.dashboard_city_label.setText("No city selected")
            self.dashboard_mode_label.setText("Online Mode" if self.online_mode else "Offline Mode")
            self.dashboard_update_label.setText("Please select a city from the home page.")
            self.score_label.setText("--")
            self.alert_badge.setText("None")
            self.alert_badge.setStyleSheet(f"background: {PALETTE['surface']}; color: {PALETTE['muted']}; border-radius: 12px; padding: 10px 14px;")
            if hasattr(self, "affected_pop_label"):
                self.affected_pop_label.setText("--")
            if hasattr(self, "dashboard_alert_banner"):
                self.dashboard_alert_banner.setVisible(False)
            return

        level = alert_level(self.city_result.score)
        color = alert_color(level)
        self.dashboard_city_label.setText(self.current_city["name"])
        self.dashboard_mode_label.setText("Online Mode" if self.online_mode else "Offline Mode")
        if self.last_data_update:
            self.dashboard_update_label.setText(f"Last data update: {self.last_data_update.strftime('%d %b %Y, %H:%M')}")
        else:
            last_up = self.current_city.get("last_updated")
            if last_up:
                if isinstance(last_up, datetime):
                    self.dashboard_update_label.setText(f"Last data update: {last_up.strftime('%d %b %Y, %H:%M')}")
                else:
                    self.dashboard_update_label.setText(f"Last data update: {str(last_up)}")
            else:
                self.dashboard_update_label.setText("Last data update: pending")
        self.score_label.setText(f"{self.city_result.score:.1f}")
        score_val = self.city_result.score
        if score_val <= 50:
            score_color = PALETTE["green"]
        elif score_val <= 70:
            score_color = PALETTE["yellow"]
        elif score_val <= 90:
            score_color = PALETTE["orange"]
        else:
            score_color = PALETTE["red"]
        self.score_label.setStyleSheet(f'font-family: "SF Mono", "Menlo"; font-size: 72px; font-weight: bold; color: {score_color};')
        self.alert_badge.setText(level)
        badge_text_color = "#111111" if level in {"Green", "Yellow"} else "#FFFFFF"
        self.alert_badge.setStyleSheet(
            f"background: {color}; color: {badge_text_color}; border-radius: 12px; padding: 10px 14px; "
            'font-family: "SF Pro Display"; font-size: 28px; font-weight: bold;'
        )
        # Always Show Alert Banner
        self.dashboard_alert_banner.setText(f"{level.upper()} ALERT")
        self.dashboard_alert_banner.setStyleSheet(f"background: {color}; color: {badge_text_color}; font-family: 'SF Pro Display'; font-size: 16px; font-weight: bold; padding: 12px; border-radius: 8px;")
        self.dashboard_alert_banner.setVisible(True)
        
        def get_zone_score(zone_id):
            val = self.zone_scores.get(int(zone_id))
            if val is None:
                val = self.zone_scores.get(str(zone_id))
            return val if val is not None else 0.0

        if self.zone_results:
            highest_id, highest = max(self.zone_results.items(), key=lambda item: item[1].score)
            highest_zone = next((zone for zone in self.current_zones if int(zone["zone_id"]) == int(highest_id)), None)
            if highest_zone:
                self.highest_zone_label.setText(f"{highest_zone['name']} ({highest.score:.1f})")
                self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["text"] + ';')
            else:
                self.highest_zone_label.setText("-")
                self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["text"] + ';')
        else:
            self.highest_zone_label.setText("-")
            self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["text"] + ';')
            
        affected_pop = sum(z["population"] for z in self.current_zones if get_zone_score(z["zone_id"]) > 50.0)
        self.affected_pop_label.setText(f"{affected_pop:,}")

        self.real_rain_label.setText(f"{self.real_rainfall:.1f} mm")
        self.real_river_label.setText(f"{self.real_river_level:.1f} m")
        self.temp_label.setText(f"{self.real_temperature:.1f} °C" if self.real_temperature is not None else "-")
        self.humidity_label.setText(f"{self.real_humidity:.0f}%" if self.real_humidity is not None else "-")
        self.wind_speed_label.setText(f"{self.real_wind_speed:.1f} km/h" if self.real_wind_speed is not None else "-")
        
        self.redraw_dashboard_map()

    def redraw_dashboard_map(self) -> None:
        if not hasattr(self, "dashboard_map_view"):
            return
        city = self.current_city
        if not city:
            self.dashboard_map_view.setHtml("<html><body style='background:#F8F6F2;'><h3 style='color:#111827;text-align:center;margin-top:20%;font-family:sans-serif;'>No city selected</h3></body></html>")
            return
            
        m = folium.Map(
            location=[city["latitude"], city["longitude"]],
            zoom_start=12,
            tiles="CartoDB positron",
            zoom_control=False
        )
        
        def get_distance(lat1, lon1, lat2, lon2):
            return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5

        def get_zone_score(zone_id):
            val = self.zone_scores.get(int(zone_id))
            if val is None:
                val = self.zone_scores.get(str(zone_id))
            return val if val is not None else 0.0

        if self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
        else:
            lat_min, lat_max = city["latitude"] - 0.1, city["latitude"] + 0.1
            lon_min, lon_max = city["longitude"] - 0.1, city["longitude"] + 0.1

        # 1. Winding River Spline
        river_lons = np.linspace(lon_min - 0.05, lon_max + 0.05, 200)
        river_points = []
        for rl in river_lons:
            # Formula matching model: lat = city_lat + 0.035 * sin(18 * (lon - city_lon)) + 0.01 * (lon - city_lon)
            rlat = city["latitude"] + 0.035 * math.sin(18.0 * (rl - city["longitude"])) + 0.01 * (rl - city["longitude"])
            river_points.append([rlat, rl])
            
        folium.PolyLine(
            locations=river_points,
            color="#2563EB",
            weight=8,
            opacity=0.85,
            tooltip="River Channel"
        ).add_to(m)

        # 2. Major Roads
        road1_m = 3.0
        road1_c = city["latitude"] - road1_m * city["longitude"]
        road2_m = -0.3
        road2_c = city["latitude"] - road2_m * city["longitude"]
        
        road_lons = np.linspace(lon_min - 0.05, lon_max + 0.05, 50)
        road1_pts = [[road1_m * rl + road1_c, rl] for rl in road_lons]
        road2_pts = [[road2_m * rl + road2_c, rl] for rl in road_lons]
        
        # Clip to map boundaries
        road1_pts = [pt for pt in road1_pts if lat_min - 0.1 <= pt[0] <= lat_max + 0.1]
        road2_pts = [pt for pt in road2_pts if lat_min - 0.1 <= pt[0] <= lat_max + 0.1]
        
        folium.PolyLine(locations=road1_pts, color="#6B7280", weight=4, opacity=0.7, tooltip="National Highway").add_to(m)
        folium.PolyLine(locations=road2_pts, color="#6B7280", weight=3.5, opacity=0.7, tooltip="State Highway").add_to(m)

        # 3. Predicted Flood Area Contour Polygons
        if self.current_model:
            grid_size = 50
            grid_lats = np.linspace(lat_min, lat_max, grid_size)
            grid_lons = np.linspace(lon_min, lon_max, grid_size)
            
            grid_vals = np.zeros((grid_size, grid_size))
            for i, lat_val in enumerate(grid_lats):
                for j, lon_val in enumerate(grid_lons):
                    risk_score = self.current_model.get_flood_risk(lat_val, lon_val, self.scenario_rainfall, self.scenario_river_level)
                    hist_freq = self.current_model.get_historical_flood_frequency(lat_val, lon_val)
                    grid_vals[i, j] = risk_score * 0.85 + hist_freq * 15.0
                    
            from scipy.ndimage import gaussian_filter
            smoothed_grid = gaussian_filter(grid_vals, sigma=2.0)
            smoothed_grid = np.clip(smoothed_grid, 0.0, 100.0)
            
            import matplotlib
            try:
                matplotlib.use('Agg', force=True)
            except Exception:
                pass
            import matplotlib.pyplot as plt
            
            fig, ax = plt.subplots()
            levels = [-1.0, 30.0, 50.0, 70.0, 85.0, 101.0]
            colors = [
                "#10B981", # Green (Safe)
                "#FBBF24", # Yellow (Low Risk)
                "#F97316", # Orange (Moderate Risk)
                "#EF4444", # Red (High Risk)
                "#7F1D1D"  # Dark Red (Flooded)
            ]
            
            cs = ax.contourf(grid_lons, grid_lats, smoothed_grid, levels=levels)
            
            if hasattr(cs, "collections"):
                for idx, collection in enumerate(cs.collections):
                    color = colors[idx]
                    paths = collection.get_paths()
                    for path in paths:
                        polys = path.to_polygons()
                        for poly in polys:
                            coords = [[float(pt[1]), float(pt[0])] for pt in poly]
                            if len(coords) >= 3:
                                folium.Polygon(
                                    locations=coords,
                                    fill=True,
                                    fill_color=color,
                                    fill_opacity=0.35,
                                    color=color,
                                    weight=0.5,
                                    opacity=0.4,
                                    smooth_factor=1.0,
                                    interactive=False
                                ).add_to(m)
            elif hasattr(cs, "allsegs"):
                for idx, level_segs in enumerate(cs.allsegs):
                    color = colors[idx]
                    for seg in level_segs:
                        coords = [[float(pt[1]), float(pt[0])] for pt in seg]
                        if len(coords) >= 3:
                            folium.Polygon(
                                locations=coords,
                                fill=True,
                                fill_color=color,
                                fill_opacity=0.35,
                                color=color,
                                weight=0.5,
                                opacity=0.4,
                                smooth_factor=1.0,
                                interactive=False
                            ).add_to(m)
            plt.close(fig)

        # 4. Affected Zones (Hexagons with Popups)
        def get_hexagon_coords(zlat, zlon, radius=0.015):
            hex_coords = []
            for k in range(6):
                angle = math.pi / 3 * k
                hex_coords.append([zlat + radius * math.sin(angle), zlon + radius * 1.2 * math.cos(angle)])
            return hex_coords

        if self.current_zones:
            for zone in self.current_zones:
                zone_id = int(zone["zone_id"])
                zone_score = get_zone_score(zone_id)
                
                if zone_score >= 90.0:
                    zone_color = "#7F1D1D"
                    suggested_action = "CRITICAL ALERT: Initiate immediate evacuation. Move to nearest shelter now. Do not traverse flooded areas."
                elif zone_score >= 70.0:
                    zone_color = "#EF4444"
                    suggested_action = "HIGH RISK: Secure essential belongings and prepare for evacuation. Monitor emergency broadcasts."
                elif zone_score >= 50.0:
                    zone_color = "#F97316"
                    suggested_action = "MODERATE RISK: Stay indoors, move valuables to upper levels, avoid low-lying roads."
                elif zone_score >= 30.0:
                    zone_color = "#FBBF24"
                    suggested_action = "LOW RISK: Alert. Monitor rainfall and river levels. Ensure emergency kit is ready."
                else:
                    zone_color = "#10B981"
                    suggested_action = "SAFE AREA: Normal vigilance. Maintain readiness and support community efforts."
                
                water_depth = max(0.0, (zone_score - 30.0) / 20.0) * (1.0 + 0.2 * max(0.0, self.scenario_river_level))
                if zone_score < 30.0:
                    water_depth = 0.0
                    
                nearest_s = min(self.current_shelters, key=lambda s: get_distance(float(s["latitude"]), float(s["longitude"]), float(zone["latitude"]), float(zone["longitude"]))) if self.current_shelters else None
                nearest_shelter_name = nearest_s["name"] if nearest_s else "None"
                
                popup_html = f"""
                <div style="font-family: 'SF Pro Text', -apple-system, sans-serif; font-size: 13px; line-height: 1.5; color: #1F2937; min-width: 220px; padding: 6px;">
                    <h4 style="margin: 0 0 8px 0; color: #111827; font-size: 15px; border-bottom: 2px solid {zone_color}; padding-bottom: 4px;">{zone['name']}</h4>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Est. Population:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{int(zone['population']):,}</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Est. Water Depth:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{water_depth:.2f} m</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Risk Score:</td><td style="padding: 4px 0; text-align: right; font-weight: bold; color: {zone_color};">{zone_score:.1f}/100</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Nearest Shelter:</td><td style="padding: 4px 0; text-align: right;">{nearest_shelter_name}</td></tr>
                    </table>
                    <div style="margin-top: 10px; background-color: #F9FAFB; border-left: 3px solid {zone_color}; padding: 6px 8px; font-size: 12px; font-style: italic; color: #374151;">
                        <strong>Suggested Action:</strong> {suggested_action}
                    </div>
                </div>
                """
                
                hex_pts = get_hexagon_coords(float(zone["latitude"]), float(zone["longitude"]), radius=0.015)
                folium.Polygon(
                    locations=hex_pts,
                    fill=True,
                    fill_color=zone_color,
                    fill_opacity=0.15,
                    color="#4B5563",
                    weight=1.5,
                    opacity=0.7,
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"{zone['name']} (Risk: {zone_score:.1f})"
                ).add_to(m)

        # 5. Evacuation Shelters (Green Markers)
        if self.current_shelters:
            for s in self.current_shelters:
                folium.Marker(
                    location=[float(s["latitude"]), float(s["longitude"])],
                    icon=folium.Icon(color="green", icon="home"),
                    tooltip=f"Shelter: {s['name']} (Capacity: {s['capacity']})"
                ).add_to(m)

        # Professional EOC HTML Legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 20px; left: 20px; width: 220px;
                    background-color: white; border: 2px solid #D6D3D1; z-index:9999; font-size:11px;
                    padding: 10px; border-radius: 8px; font-family: sans-serif; opacity: 0.95; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <b style="font-size:12px; color:#111827;">EOC Flood Extent Legend</b><br>
            
            <div style="margin-top: 6px;">
                <b>Predicted Flood Spread</b><br>
                <div style="margin-top: 4px;">
                    <span style="display:inline-block; width:12px; height:12px; background-color:#7F1D1D; vertical-align:middle; margin-right:4px;"></span> Flooded Areas (Dark Red)<br>
                    <span style="display:inline-block; width:12px; height:12px; background-color:#EF4444; vertical-align:middle; margin-right:4px;"></span> High Risk Areas (Red)<br>
                    <span style="display:inline-block; width:12px; height:12px; background-color:#F97316; vertical-align:middle; margin-right:4px;"></span> Moderate Risk (Orange)<br>
                    <span style="display:inline-block; width:12px; height:12px; background-color:#FBBF24; vertical-align:middle; margin-right:4px;"></span> Low Risk (Yellow)<br>
                    <span style="display:inline-block; width:12px; height:12px; background-color:#10B981; vertical-align:middle; margin-right:4px;"></span> Safe Areas (Green)<br>
                </div>
            </div>
            
            <div style="margin-top: 6px; border-top: 1px solid #E5E7EB; padding-top: 4px;">
                <span style="color:#2563EB; font-weight:bold;">▰▰</span> River spline<br>
                <span style="color:#6B7280; font-weight:bold;">▰▰</span> Road Networks<br>
                <span style="color:green; font-weight:bold;">🏠</span> Evacuation Shelter
            </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
            
        html = m.get_root().render()
        self.dashboard_map_view.setHtml(html)

    def refresh_all(self) -> None:
        self.refresh_city_combos()
        self.update_from_sliders()
        self.refresh_trends()

    def redraw_map(self) -> None:
        if not hasattr(self, "map_view"):
            return
        city = self.current_city
        if not city:
            self.map_view.setHtml("<html><body style='background:#F8F6F2;'><h3 style='color:#111827;text-align:center;margin-top:20%;font-family:sans-serif;'>No city selected</h3></body></html>")
            return
            
        m = folium.Map(
            location=[city["latitude"], city["longitude"]],
            zoom_start=12,
            tiles="CartoDB positron"
        )
        
        def get_distance(lat1, lon1, lat2, lon2):
            return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5

        def get_dist_km(lat1, lon1, lat2, lon2):
            return (((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5) * 111.32

        # Bounding box for grid
        if self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
        else:
            lat_min, lat_max = city["latitude"] - 0.1, city["latitude"] + 0.1
            lon_min, lon_max = city["longitude"] - 0.1, city["longitude"] + 0.1

        # Reusable helper to generate contour polygons for GIS layers
        def add_contour_layer(grid_data_vals, colors, levels, layer_name=None):
            grid_lats = np.linspace(lat_min, lat_max, grid_data_vals.shape[0])
            grid_lons = np.linspace(lon_min, lon_max, grid_data_vals.shape[1])
            
            from scipy.ndimage import gaussian_filter
            smoothed = gaussian_filter(grid_data_vals, sigma=2.0)
            smoothed = np.clip(smoothed, 0.0, 100.0)
            
            import matplotlib
            try:
                matplotlib.use('Agg', force=True)
            except Exception:
                pass
            import matplotlib.pyplot as plt
            
            fig, ax = plt.subplots()
            cs = ax.contourf(grid_lons, grid_lats, smoothed, levels=levels)
            
            def get_poly_popup_html(plat, plon, val, color):
                if val >= 90.0:
                    cat = "Extreme Density"
                elif val >= 75.0:
                    cat = "Very High Density"
                elif val >= 55.0:
                    cat = "High Density"
                elif val >= 35.0:
                    cat = "Medium Density"
                elif val >= 15.0:
                    cat = "Low Density"
                else:
                    cat = "Very Low Density"
                
                infra_count = 0
                if self.current_infra:
                    infra_count = sum(1 for inf in self.current_infra if ((plat - float(inf["latitude"]))**2 + (plon - float(inf["longitude"]))**2)**0.5 <= 0.02)
                
                nearest_s = min(self.current_shelters, key=lambda s: ((plat - float(s["latitude"]))**2 + (plon - float(s["longitude"]))**2)**0.5) if self.current_shelters else None
                nearest_s_name = nearest_s["name"] if nearest_s else "None"
                
                elev = self.current_model.get_elevation(plat, plon) if self.current_model else 15.0
                risk = self.current_model.get_flood_risk(plat, plon, self.scenario_rainfall, self.scenario_river_level) if self.current_model else 0.0
                
                return f"""
                <div style="font-family: 'SF Pro Text', -apple-system, sans-serif; font-size: 13px; line-height: 1.5; color: #1F2937; min-width: 220px; padding: 6px;">
                    <h4 style="margin: 0 0 8px 0; color: #111827; font-size: 15px; border-bottom: 2px solid {color}; padding-bottom: 4px;">Population Density Detail</h4>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Category:</td><td style="padding: 4px 0; text-align: right; font-weight: bold; color: {color};">{cat}</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Relative Density:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{val:.1f}%</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Nearby Infra Count:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{infra_count}</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Nearest Shelter:</td><td style="padding: 4px 0; text-align: right;">{nearest_s_name}</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Elevation:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{int(elev)} m</td></tr>
                        <tr style="border-bottom: 1px solid #E5E7EB;"><td style="padding: 4px 0; font-weight: 600; color: #4B5563;">Current Flood Risk:</td><td style="padding: 4px 0; text-align: right; font-weight: bold;">{risk:.1f}/100</td></tr>
                    </table>
                </div>
                """

            def add_poly_to_map(coords, color, idx):
                if layer_name == "population" and len(coords) > 0:
                    plat_avg = sum(c[0] for c in coords) / len(coords)
                    plon_avg = sum(c[1] for c in coords) / len(coords)
                    level_bounds = levels
                    val_avg = (level_bounds[idx] + level_bounds[idx+1]) / 2.0
                    p_html = get_poly_popup_html(plat_avg, plon_avg, val_avg, color)
                    
                    folium.Polygon(
                        locations=coords,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.35,
                        color=color,
                        weight=0.5,
                        opacity=0.4,
                        smooth_factor=1.0,
                        interactive=True,
                        popup=folium.Popup(p_html, max_width=300),
                        tooltip=f"Density: {val_avg:.0f}%"
                    ).add_to(m)
                else:
                    folium.Polygon(
                        locations=coords,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.35,
                        color=color,
                        weight=0.5,
                        opacity=0.4,
                        smooth_factor=1.0,
                        interactive=False
                    ).add_to(m)

            if hasattr(cs, "collections"):
                for idx, collection in enumerate(cs.collections):
                    color = colors[idx]
                    paths = collection.get_paths()
                    for path in paths:
                        polys = path.to_polygons()
                        for poly in polys:
                            coords = [[float(pt[1]), float(pt[0])] for pt in poly]
                            if len(coords) >= 3:
                                add_poly_to_map(coords, color, idx)
            elif hasattr(cs, "allsegs"):
                for idx, level_segs in enumerate(cs.allsegs):
                    color = colors[idx]
                    for seg in level_segs:
                        coords = [[float(pt[1]), float(pt[0])] for pt in seg]
                        if len(coords) >= 3:
                            add_poly_to_map(coords, color, idx)
            plt.close(fig)

        # Helper to compute popup HTML with exactly 9 fields
        def get_popup_html(name, el_type, plat, plon, status_override=None):
            elev = 15.0
            river_dist = 0.0
            risk_score = 0.0
            if self.current_model:
                elev = self.current_model.get_elevation(plat, plon)
                river_dist = self.current_model.get_river_distance(plat, plon) * 111.32
                risk_score = self.current_model.get_flood_risk(plat, plon, self.scenario_rainfall, self.scenario_river_level)
            else:
                elev = float(city["elevation"])
                river_dist = 1.0
                risk_score = self.city_result.score
                
            risk_lvl = alert_level(risk_score)
            
            # Status
            if status_override:
                status = status_override
            else:
                if risk_score >= 90.0:
                    status = "Critical Alert" if el_type not in ["shelter", "evacuation_point"] else "Inaccessible"
                elif risk_score >= 70.0:
                    status = "Under Alert"
                else:
                    status = "Operational" if el_type not in ["shelter", "evacuation_point"] else "Active"
                    
            # Population Served
            pop_served = int(self.current_model.get_population_density(plat, plon) * 15000) if self.current_model else 5000
            
            # Nearest Shelter
            nearest_s = min(self.current_shelters, key=lambda s: get_distance(float(s["latitude"]), float(s["longitude"]), plat, plon)) if self.current_shelters else None
            nearest_s_name = nearest_s["name"] if nearest_s else "None"
            if el_type in ["shelter", "evacuation_point"] and len(self.current_shelters) > 1:
                other_s = min([s for s in self.current_shelters if s["name"] != name], key=lambda s: get_distance(float(s["latitude"]), float(s["longitude"]), plat, plon))
                nearest_s_name = other_s["name"]
            elif el_type in ["shelter", "evacuation_point"]:
                nearest_s_name = "N/A (Self)"
                
            # Recommendation
            if "hospital" in el_type:
                if "Critical" in status:
                    reco = "Evacuate ICU patients, deploy flood barriers."
                elif "Under" in status:
                    reco = "Prepare emergency power backups, monitor water levels."
                else:
                    reco = "Maintain normal operations, monitor updates."
            elif "school" in el_type:
                if "Critical" in status:
                    reco = "Suspend classes immediately, open as emergency assembly."
                elif "Under" in status:
                    reco = "Prepare for temporary suspension, secure school archives."
                else:
                    reco = "Classes operational, monitor weather forecasts."
            elif el_type in ["power_station", "water_treatment"]:
                if "Critical" in status:
                    reco = "Shut down critical grids, deploy high-capacity pumps."
                elif "Under" in status:
                    reco = "Activate secondary containment, secure fuel supplies."
                else:
                    reco = "Grid operational, normal capacity."
            elif el_type in ["shelter", "evacuation_point"]:
                if "Inaccessible" in status:
                    reco = "Redirect evacuees to nearest safe assembly point."
                elif "Under" in status:
                    reco = "Capacity running high. Monitor local ingress."
                else:
                    reco = "Active. Accepting evacuees."
            elif "flood" in el_type:
                reco = "Historically affected zone. Avoid low-lying roadways."
            else:
                reco = "Monitor local conditions and EOC bulletins."
                
            return f"""
            <div style="font-family: 'SF Pro Text', sans-serif; font-size:12px; line-height: 1.4; width: 240px; color: #111827;">
                <b>Name:</b> {name}<br>
                <b>Type:</b> {el_type.replace('_', ' ').title()}<br>
                <b>Elevation:</b> {int(elev)} m<br>
                <b>Risk Level:</b> {risk_lvl}<br>
                <b>Population Served:</b> {pop_served:,}<br>
                <b>Nearest Shelter:</b> {nearest_s_name}<br>
                <b>Distance to River:</b> {river_dist:.2f} km<br>
                <b>Status:</b> {status}<br>
                <b>Recommendation:</b> {reco}
            </div>
            """

        # 1. Population density layer (Contour Polygons)
        if self.layer_population.isChecked() and self.current_model:
            grid_size = 60  # Higher grid resolution for finer detail
            grid_lats = np.linspace(lat_min, lat_max, grid_size)
            grid_lons = np.linspace(lon_min, lon_max, grid_size)
            
            grid_vals = np.zeros((grid_size, grid_size))
            for i, lt in enumerate(grid_lats):
                for j, ln in enumerate(grid_lons):
                    grid_vals[i, j] = self.current_model.get_population_density(lt, ln) * 100.0
                    
            pop_colors = ["#E5E7EB", "#93C5FD", "#14B8A6", "#FBBF24", "#F97316", "#EF4444"]
            pop_levels = [-1.0, 15.0, 35.0, 55.0, 75.0, 90.0, 101.0]  # 6 soft, professional categories
            add_contour_layer(grid_vals, pop_colors, pop_levels, layer_name="population")
            
        # 2. Flood Risk heatmap layer (Contour Polygons)
        if self.layer_risk.isChecked() and self.current_zones and self.current_model:
            risk_vals = [self.zone_scores.get(int(z["zone_id"]), 0.0) / 100.0 for z in self.current_zones]
            
            grid_size = 40
            grid_lats = np.linspace(lat_min, lat_max, grid_size)
            grid_lons = np.linspace(lon_min, lon_max, grid_size)
            
            zone_coords = np.array([[float(z["latitude"]), float(z["longitude"])] for z in self.current_zones])
            zone_vals = np.array(risk_vals)
            
            grid_vals = np.zeros((grid_size, grid_size))
            for i, lt in enumerate(grid_lats):
                for j, ln in enumerate(grid_lons):
                    dists = np.sqrt(np.sum((zone_coords - np.array([lt, ln]))**2, axis=1))
                    zero_dist_idx = np.where(dists < 1e-6)[0]
                    if len(zero_dist_idx) > 0:
                        interp_risk = zone_vals[zero_dist_idx[0]]
                    else:
                        weights = 1.0 / (dists ** 2)
                        interp_risk = np.sum(weights * zone_vals) / np.sum(weights)
                        
                    model_risk = self.current_model.get_flood_risk(lt, ln, self.scenario_rainfall, self.scenario_river_level) / 100.0
                    grid_vals[i, j] = (0.4 * interp_risk + 0.6 * model_risk) * 100.0
                    
            risk_colors = ["#2563EB", "#10B981", "#FBBF24", "#F97316", "#EF4444"]
            risk_levels = [-1.0, 20.0, 40.0, 60.0, 80.0, 101.0]
            add_contour_layer(grid_vals, risk_colors, risk_levels)
            
        # 3. Elevation heatmap layer (Contour Polygons)
        if self.layer_elevation.isChecked() and self.current_model:
            grid_size = 40
            grid_lats = np.linspace(lat_min, lat_max, grid_size)
            grid_lons = np.linspace(lon_min, lon_max, grid_size)
            
            grid_vals = np.zeros((grid_size, grid_size))
            for i, lt in enumerate(grid_lats):
                for j, ln in enumerate(grid_lons):
                    grid_vals[i, j] = self.current_model.get_elevation(lt, ln)
                    
            min_e = np.min(grid_vals)
            max_e = np.max(grid_vals)
            span = max_e - min_e if max_e > min_e else 1.0
            normalized = (grid_vals - min_e) / span * 100.0
            
            elev_colors = ["#7F1D1D", "#F97316", "#FBBF24", "#86EFAC", "#064E3B"]
            elev_levels = [-1.0, 20.0, 40.0, 60.0, 80.0, 101.0]
            add_contour_layer(normalized, elev_colors, elev_levels)
            
        # 4. Historical flood extent layer
        if self.layer_history.isChecked() and self.current_model:
            grid_size = 40
            grid_lats = np.linspace(lat_min, lat_max, grid_size)
            grid_lons = np.linspace(lon_min, lon_max, grid_size)
            
            grid_vals = np.zeros((grid_size, grid_size))
            for i, lt in enumerate(grid_lats):
                for j, ln in enumerate(grid_lons):
                    grid_vals[i, j] = self.current_model.get_historical_flood_frequency(lt, ln)
                    
            from scipy.ndimage import gaussian_filter
            smoothed_grid = gaussian_filter(grid_vals, sigma=2.0)
            
            grid_data = []
            for i, lt in enumerate(grid_lats):
                for j, ln in enumerate(grid_lons):
                    grid_data.append([lt, ln, float(smoothed_grid[i, j])])
                    
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.25,
                    gradient={0.2: '#93C5FD', 0.6: '#3B82F6', 1.0: '#1D4ED8'}
                ).add_to(m)
                
            # Place blue markers for historical flood incidents
            for pt in self.current_historical_flood_points:
                popup_content = get_popup_html(
                    pt["name"], 
                    "historical_flood_point", 
                    pt["latitude"], 
                    pt["longitude"],
                    status_override="Historically Flooded"
                )
                folium.Marker(
                    location=[pt["latitude"], pt["longitude"]],
                    icon=folium.Icon(color="blue", icon="tint"),
                    popup=folium.Popup(popup_content, max_width=300)
                ).add_to(m)
                    
        # 5. Critical infrastructure layer
        if self.layer_infra.isChecked() and self.current_infra:
            for inf in self.current_infra:
                # Setup icons based on type
                inf_type = inf["type"].lower()
                if "hospital" in inf_type:
                    icon_name = "plus"
                    color = "red"
                elif "school" in inf_type:
                    icon_name = "book"
                    color = "blue"
                elif "police" in inf_type:
                    icon_name = "shield"
                    color = "darkblue"
                elif "power" in inf_type:
                    icon_name = "flash"
                    color = "orange"
                elif "fire" in inf_type:
                    icon_name = "fire"
                    color = "red"
                elif "water" in inf_type:
                    icon_name = "tint"
                    color = "cadetblue"
                else:
                    icon_name = "info-sign"
                    color = "purple"
                    
                popup_content = get_popup_html(inf["name"], inf["type"], inf["latitude"], inf["longitude"])
                
                folium.Marker(
                    location=[inf["latitude"], inf["longitude"]],
                    icon=folium.Icon(color=color, icon=icon_name),
                    popup=folium.Popup(popup_content, max_width=300)
                ).add_to(m)
                
        # 6. Evacuation Points layer
        if self.layer_evac.isChecked() and self.current_shelters:
            for idx, s in enumerate(self.current_shelters):
                types = ["Shelter", "Assembly Point", "Emergency Camp", "Rescue Base"]
                e_type = types[idx % len(types)]
                
                if e_type == "Shelter":
                    icon_name = "home"
                elif e_type == "Assembly Point":
                    icon_name = "flag"
                elif e_type == "Emergency Camp":
                    icon_name = "fire"
                else:
                    icon_name = "star"
                    
                popup_content = get_popup_html(s["name"], "evacuation_point", s["latitude"], s["longitude"])
                
                folium.Marker(
                    location=[s["latitude"], s["longitude"]],
                    icon=folium.Icon(color="green", icon=icon_name),
                    popup=folium.Popup(popup_content, max_width=300)
                ).add_to(m)
                
        # Professional EOC HTML Legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 20px; left: 20px; width: 280px; max-height: 380px; overflow-y: auto;
                    background-color: white; border: 2px solid #D6D3D1; z-index:9999; font-size:11px;
                    padding: 12px; border-radius: 8px; font-family: sans-serif; opacity: 0.95; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <b style="font-size:13px; color:#111827;">EOC Operational Legend</b><br>
            
            <div style="margin-top: 8px;">
                <b>Flood Risk (Continuous)</b><br>
                <div style="background: linear-gradient(to right, blue, green, yellow, orange, red); height: 8px; border-radius: 4px; margin-top: 4px; margin-bottom: 2px;"></div>
                <span style="float: left; font-size:9px;">Very Low</span>
                <span style="float: right; font-size:9px;">Critical</span>
                <div style="clear: both;"></div>
            </div>
            
            <div style="margin-top: 8px;">
                <b>Population Density (Contour Scale)</b><br>
                <div style="background: linear-gradient(to right, #E5E7EB, #93C5FD, #14B8A6, #FBBF24, #F97316, #EF4444); height: 8px; border-radius: 4px; margin-top: 4px; margin-bottom: 2px;"></div>
                <span style="float: left; font-size:9px;">Very Low</span>
                <span style="float: right; font-size:9px;">Extreme</span>
                <div style="clear: both;"></div>
            </div>
            
            <div style="margin-top: 8px;">
                <b>Elevation (Continuous)</b><br>
                <div style="background: linear-gradient(to right, red, orange, yellow, green, #064E3B); height: 8px; border-radius: 4px; margin-top: 4px; margin-bottom: 2px;"></div>
                <span style="float: left; font-size:9px;">Lowest</span>
                <span style="float: right; font-size:9px;">Highest</span>
                <div style="clear: both;"></div>
            </div>
            
            <div style="margin-top: 8px; border-top: 1px solid #E5E7EB; padding-top: 6px;">
                <b>Operational Assets & Nodes</b><br>
                <table style="width:100%; border-collapse:collapse; margin-top:4px;">
                    <tr>
                        <td><span style="color:red; font-weight:bold; font-size:12px;">✚</span> Hospital</td>
                        <td><span style="color:blue; font-weight:bold; font-size:12px;">📘</span> School</td>
                    </tr>
                    <tr>
                        <td><span style="color:darkblue; font-weight:bold; font-size:12px;">🛡️</span> Police</td>
                        <td><span style="color:red; font-weight:bold; font-size:12px;">🔥</span> Fire Station</td>
                    </tr>
                    <tr>
                        <td><span style="color:orange; font-weight:bold; font-size:12px;">⚡</span> Power Station</td>
                        <td><span style="color:cadetblue; font-weight:bold; font-size:12px;">💧</span> Water Works</td>
                    </tr>
                    <tr>
                        <td><span style="color:purple; font-weight:bold; font-size:12px;">🏛️</span> Relief Center</td>
                        <td><span style="color:blue; font-weight:bold; font-size:12px;">📍</span> Flood Zone</td>
                    </tr>
                    <tr>
                        <td colspan="2"><span style="color:green; font-weight:bold; font-size:12px;">🏠</span> Evacuation Point (Green)</td>
                    </tr>
                </table>
            </div>
        </div>
        '''
        
        m.get_root().html.add_child(folium.Element(legend_html))
            
        # JS click handler script
        click_js = """
        <script>
        function addClickCallback() {
            var map_elements = document.getElementsByClassName('folium-map');
            if (map_elements.length > 0) {
                var map_id = map_elements[0].id;
                var map_obj = window[map_id];
                if (map_obj) {
                    map_obj.on('click', function(e) {
                        window.location.href = 'pyqt://click?lat=' + e.latlng.lat + '&lng=' + e.latlng.lng;
                    });
                }
            }
        }
        setTimeout(addClickCallback, 500);
        </script>
        """
        m.get_root().html.add_child(folium.Element(click_js))
        
        html = m.get_root().render()
        self.map_view.setHtml(html)

    def refresh_evacuation(self) -> None:
        if not self.planner:
            return
        plan = self.planner.plan(self.zone_scores)
        
        # Populate Summary Card Labels
        total_teams = sum(row['teams'] for row in plan)
        total_boats = sum(row['boats'] for row in plan)
        critical_zones = sum(1 for row in plan if row['priority_score'] > 100000)
        
        self.evac_teams_label.setText(str(total_teams))
        self.evac_boats_label.setText(str(total_boats))
        self.evac_critical_zones_label.setText(str(critical_zones))
        
        self.priority_table.setRowCount(len(plan))
        for row_idx, row in enumerate(plan):
            score = row['priority_score']
            if score > 100000:
                prio_str = f"Critical ({score/1000:.0f}K)"
            elif score > 50000:
                prio_str = f"High ({score/1000:.0f}K)"
            elif score > 10000:
                prio_str = f"Medium ({score/1000:.0f}K)"
            else:
                prio_str = f"Low ({score/1000:.0f}K)"
                
            values = [
                row["zone"]["name"],
                f"{row['priority_score'] / 1000:.0f}",
                row["shelter"]["name"],
                f"{row['distance_km']:.1f} km",
                prio_str,
                str(row["teams"]),
                str(row["boats"])
            ]
            for col, value in enumerate(values):
                self.priority_table.setItem(row_idx, col, QTableWidgetItem(value))
        self.priority_table.resizeColumnsToContents()
        # Shelter occupancy removed
        self.route_select_combo.blockSignals(True)
        current_selection = self.route_select_combo.currentText()
        self.route_select_combo.clear()
        self.route_select_combo.addItem("All Routes")
        for row in plan:
            self.route_select_combo.addItem(row["zone"]["name"])
        index = self.route_select_combo.findText(current_selection)
        if index >= 0:
            self.route_select_combo.setCurrentIndex(index)
        else:
            self.route_select_combo.setCurrentIndex(0)
        self.route_select_combo.blockSignals(False)
        self.redraw_routes(plan)

    def redraw_routes(self, plan: list[dict]) -> None:
        if not hasattr(self, "route_view"):
            return
        city = self.current_city
        if not city:
            self.route_view.setHtml("<html><body style='background:#F8F6F2;'><h3 style='color:#111827;text-align:center;margin-top:20%;font-family:sans-serif;'>No city selected</h3></body></html>")
            return
            
        m = folium.Map(
            location=[city["latitude"], city["longitude"]],
            zoom_start=12,
            tiles="CartoDB positron"
        )
        
        bounds = []
        for zone in self.current_zones:
            score = self.zone_scores.get(int(zone["zone_id"]), 0)
            lat, lon = float(zone["latitude"]), float(zone["longitude"])
            bounds.append((lat, lon))
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="#111827",
                fill=True,
                fill_color=alert_color(alert_level(score)),
                fill_opacity=0.9,
                popup=zone["name"]
            ).add_to(m)
            
        for shelter in self.current_shelters:
            lat, lon = float(shelter["latitude"]), float(shelter["longitude"])
            bounds.append((lat, lon))
            folium.Marker(
                location=[lat, lon],
                icon=folium.Icon(color="blue", icon="home"),
                popup=shelter["name"]
            ).add_to(m)
            
        node_lookup = {
            f"zone:{zone['zone_id']}": zone for zone in self.current_zones
        } | {f"shelter:{shelter['shelter_id']}": shelter for shelter in self.current_shelters}
        
        selected = self.route_select_combo.currentText()
        for row in plan:
            if selected != "All Routes" and row["zone"]["name"] != selected:
                continue
            coords = [(node_lookup[node]["latitude"], node_lookup[node]["longitude"]) for node in row["path"] if node in node_lookup]
            if len(coords) >= 2:
                folium.PolyLine(coords, color="#10B981", weight=4, opacity=0.8, dash_array="10").add_to(m)
        
        if bounds:
            m.fit_bounds(bounds)
                
        html = m.get_root().render()
        self.route_view.setHtml(html)

    def refresh_trends(self) -> None:
        if not hasattr(self, "canvas_rain") or not self.current_city:
            return
        
        city_id = int(self.current_city["city_id"])
        
        def task() -> dict:
            logs = self.cache_service.get_simulation_logs(city_id)
            return {"logs": logs}
            
        def success(payload: dict) -> None:
            logs = payload["logs"]
            history = self.current_history
            
            # 1. Rainfall History
            ax = self.canvas_rain.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            ax.plot([float(h["rainfall_mm"]) for h in history], color=PALETTE["accent"])
            ax.set_ylabel("Rainfall (mm)", color=PALETTE["muted"])
            ax.tick_params(colors=PALETTE["muted"])
            self.canvas_rain.draw_idle()
            
            # 2. River Level History
            ax = self.canvas_river.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            ax.plot([float(h.get("river_level_m", 1.5)) for h in history], color="#3B82F6")
            ax.set_ylabel("River Level (m)", color=PALETTE["muted"])
            ax.tick_params(colors=PALETTE["muted"])
            self.canvas_river.draw_idle()
            
            # 3. Flood Risk Trend
            ax = self.canvas_risk.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            risk_scores = [float(l["risk_score"]) for l in reversed(logs[:30])] if logs else [self.city_result.score]
            ax.plot(risk_scores, color=PALETTE["red"])
            ax.set_ylabel("Risk Score", color=PALETTE["muted"])
            ax.set_ylim(0, 100)
            ax.tick_params(colors=PALETTE["muted"])
            self.canvas_risk.draw_idle()
            
            # 4. Temperature & Humidity Trend
            ax = self.canvas_temp.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            temps = [float(self.current_city.get("temperature", 25)) + (i % 3 - 1)*0.5 for i in range(20)]
            hums = [float(self.current_city.get("humidity", 60)) + (i % 5 - 2)*1.2 for i in range(20)]
            ax.plot(temps, color="#F59E0B", label="Temp (°C)")
            ax.plot(hums, color="#10B981", label="Humidity (%)")
            ax.legend(facecolor=PALETTE["panel"], labelcolor=PALETTE["text"])
            ax.tick_params(colors=PALETTE["muted"])
            self.canvas_temp.draw_idle()
            
            # 5. Population At Risk
            ax = self.canvas_pop.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            if self.current_zones:
                names = [z["name"].split()[0] for z in self.current_zones]
                pops = [float(z["population"]) for z in self.current_zones]
                ax.bar(names, pops, color=PALETTE["accent"])
            ax.tick_params(colors=PALETTE["muted"], labelrotation=45)
            self.canvas_pop.draw_idle()
            
            # 6. Alert Level Timeline
            ax = self.canvas_alert.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            if logs:
                levels = [alert_level(float(l["risk_score"])) for l in reversed(logs[:30])]
                level_map = {"Green": 1, "Yellow": 2, "Orange": 3, "Red": 4}
                y_vals = [level_map.get(l, 1) for l in levels]
                ax.step(range(len(y_vals)), y_vals, color=PALETTE["yellow"])
                ax.set_yticks([1, 2, 3, 4])
                ax.set_yticklabels(["Green", "Yellow", "Orange", "Red"])
            ax.tick_params(colors=PALETTE["muted"])
            self.canvas_alert.draw_idle()
            
        self.run_background(task, success)

    def home_status_card(self, title: str, value: str, color: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HomeCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet('font-family: "SF Pro Text"; font-size: 16px; color: #666666;')
        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-family: "SF Pro Display"; font-size: 24px; font-weight: 700; color: {color};')
        frame.value_label = value_label
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame

    def set_home_status(self, frame: QFrame, value: str, color: str) -> None:
        frame.value_label.setText(value)
        frame.value_label.setStyleSheet(f'font-family: "SF Pro Display"; font-size: 24px; font-weight: 700; color: {color};')

    def update_home_status_cards(self) -> None:
        if not hasattr(self, "database_status_card"):
            return
        
        # Check MySQL in a background task to avoid blocking the UI thread!
        def check_task() -> dict:
            return {
                "mysql": self.cache_service.check_mysql(),
                "model": MODEL_PATH.exists()
            }
            
        def success(res: dict) -> None:
            if res["mysql"]:
                self.set_home_status(self.database_status_card, "Ready", PALETTE["green"])
            else:
                self.set_home_status(self.database_status_card, "Error", PALETTE["red"])
                
            # Weather API Status
            if self.online_mode:
                def check_api() -> dict:
                    internet = check_internet()
                    api = check_api_availability() if internet else False
                    return {"internet": internet, "api": api}
                    
                def success_api(api_res: dict) -> None:
                    if api_res["internet"] and api_res["api"]:
                        self.set_home_status(self.weather_status_card, "Connected", PALETTE["green"])
                        if hasattr(self, "btn_refresh_all"):
                            self.btn_refresh_all.setVisible(True)
                    else:
                        self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
                        if hasattr(self, "btn_refresh_all"):
                            self.btn_refresh_all.setVisible(False)
                            
                def failed_api(msg: str) -> None:
                    self.set_home_status(self.weather_status_card, "Error", PALETTE["red"])
                    if hasattr(self, "btn_refresh_all"):
                        self.btn_refresh_all.setVisible(False)
                        
                self.set_home_status(self.weather_status_card, "Fetching", PALETTE["yellow"])
                self.run_background(check_api, success_api, failed_api)
            else:
                self.set_home_status(self.weather_status_card, "Offline", PALETTE["muted"])
                if hasattr(self, "btn_refresh_all"):
                    self.btn_refresh_all.setVisible(False)
                
            # Risk Model Status
            if res["model"]:
                self.set_home_status(self.model_status_card, "Loaded", PALETTE["green"])
            else:
                self.set_home_status(self.model_status_card, "Error", PALETTE["red"])
                
        self.run_background(check_task, success)

    def update_search_prompt(self) -> None:
        if not hasattr(self, "home_message"):
            return
        if self.online_mode:
            self.home_message.setText("Press Enter to check local data first, then download city data if needed.")
        else:
            self.home_message.setText("Press Enter to search local city data.")

    def run_city_search(self) -> None:
        query = self.city_search.text().strip()
        if not query:
            return
            
        online = self.online_mode
        if hasattr(self, "home_loading"):
            self.home_loading.setText("Searching...")
            
        def task() -> dict:
            # 1. Check if city exists in MySQL cache
            exists = self.cache_service.city_exists(query)
            if exists:
                bundle = self.cache_service.load_city(query)
                city_name = bundle["city"]["name"] if bundle else query
                return {"status": "local", "city_name": city_name}
                
            if not online:
                return {"status": "offline_missing"}
                
            # 2. Fetch city from API (Geocode + Elevation + Weather)
            location_data = self.city_service.search_and_fetch_city(query)
            weather_data = self.weather_service.fetch_weather(location_data["latitude"], location_data["longitude"])
            
            # Generate default city layout bundle
            next_id = self.cache_service.get_next_city_id()
            city_bundle = self.city_service.generate_default_city_bundle(
                city_id=next_id,
                city_name=location_data["city"],
                state=location_data["state"],
                latitude=location_data["latitude"],
                longitude=location_data["longitude"],
                elevation=location_data["elevation"],
                current_rainfall=weather_data["rainfall_mm"]
            )
            
            # Set weather values on the city record in the bundle
            city_bundle["city"]["temperature"] = weather_data["temperature"]
            city_bundle["city"]["humidity"] = weather_data["humidity"]
            city_bundle["city"]["wind_speed"] = weather_data["wind_speed"]
            
            # Generate placeholder map for new city
            ensure_placeholder_maps([{"name": location_data["city"]}])
            
            # 3. Store everything in MySQL
            self.cache_service.save_city(city_bundle)
            
            return {"status": "downloaded", "city_name": location_data["city"]}
            
        def success(result: dict) -> None:
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
                
            status = result["status"]
            if status == "local":
                city_name = result["city_name"]
                if hasattr(self, "home_message"):
                    self.home_message.setText("✓ Loaded from local database")
                self.update_cities_list_and_load(city_name, "Loaded from local database")
                
            elif status == "offline_missing":
                if hasattr(self, "home_message"):
                    self.home_message.setText("✗ City not found")
                QMessageBox.information(self, "City Not Available", "City not found in local database.")
                
            elif status == "downloaded":
                city_name = result["city_name"]
                if hasattr(self, "home_message"):
                    self.home_message.setText("✓ Downloaded and cached successfully")
                self.update_cities_list_and_load(city_name, "Downloaded and cached successfully")
                
        def failed(msg: str) -> None:
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            
            if "not found" in msg.lower() or "404" in msg:
                if hasattr(self, "home_message"):
                    self.home_message.setText("✗ City not found")
                QMessageBox.warning(self, "Search Error", "✗ City not found")
                logger.error(f"API failure: City not found: {query}")
            else:
                if hasattr(self, "home_message"):
                    self.home_message.setText("✗ No internet connection")
                QMessageBox.warning(self, "Search Error", "✗ No internet connection")
                logger.error(f"API failure: {msg}")

        self.run_background(task, success, failed)

    def start_initialization(self) -> None:
        if hasattr(self, "home_loading"):
            self.home_loading.setText("Initializing database...")
            
        def init_task() -> list[dict]:
            # Ensure model files are ready locally
            ensure_startup_assets()
            # Initialize DB tables if missing
            self.cache_service.initialize_db_schema_if_needed()
            # Fetch all cities from DB
            return self.cache_service.get_all_cities()
            
        def init_success(cities: list[dict]) -> None:
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            self.update_home_status_cards()
            if cities:
                self.cities_list = cities
                self.current_city = None
                self.refresh_city_combos()
                self.apply_db_overview(cities)
            else:
                self.home_message.setText("✗ Database failed to initialize.")
                
        def init_failed(msg: str) -> None:
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            self.home_message.setText(f"✗ Init failed: {msg}")
            
        self.run_background(init_task, init_success, init_failed)

    def update_cities_list_and_load(self, city_name: str, dialog_msg: str) -> None:
        def task() -> list[dict]:
            return self.cache_service.get_all_cities()
            
        def success(cities: list[dict]) -> None:
            self.cities_list = cities
            self.refresh_city_combos()
            self.apply_db_overview(cities)
            self.load_city(city_name)
            self.show_city_dialog(dialog_msg)
            
        self.run_background(task, success)

    def show_city_dialog(self, message: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("City Data Ready")
        dialog.setText(message)
        open_button = dialog.addButton("Open Dashboard", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == open_button:
            self.open_dashboard()

    def open_dashboard(self) -> None:
        self.show_screen(1)

    def check_ollama(self) -> None:
        def task() -> dict:
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=1.5)
                response.raise_for_status()
                models = [m.get("name") for m in response.json().get("models", [])]
                if "qwen2.5:3b" in models:
                    return {"status": "ok", "model": "qwen2.5:3b"}
                elif "phi3:mini" in models:
                    return {"status": "ok", "model": "phi3:mini"}
                else:
                    return {"status": "no_model"}
            except Exception:
                return {"status": "offline"}

        def success(res: dict) -> None:
            status = res["status"]
            if status == "ok":
                self.active_model = res["model"]
                self.ai_status.setText("FloodGuard AI Advisor Online")
                self.btn_install_model.hide()
                self.ai_send.setEnabled(True)
                self.ai_input.setEnabled(True)
            elif status == "no_model":
                self.ai_status.setText("AI Advisor Offline (Model Missing)")
                self.ai_send.setEnabled(False)
                self.ai_input.setEnabled(False)
                self.btn_install_model.setText("Install Model")
                self.btn_install_model.show()
            else:
                self.ai_status.setText("AI Advisor Offline (Ollama not running)")
                self.btn_install_model.hide()
                self.ai_send.setEnabled(False)
                self.ai_input.setEnabled(False)

        def failed(msg: str) -> None:
            self.ai_status.setText("AI Advisor Offline")
            self.btn_install_model.hide()
            self.ai_send.setEnabled(False)
            self.ai_input.setEnabled(False)

        self.run_background(task, success, failed)

    def pull_ollama_model(self) -> None:
        self.btn_install_model.setEnabled(False)
        self.btn_install_model.setText("Downloading...")
        self.ai_status.setText("Downloading qwen2.5:3b... (This may take a while)")
        
        def task() -> bool:
            try:
                response = requests.post("http://localhost:11434/api/pull", json={"name": "qwen2.5:3b"}, timeout=600)
                response.raise_for_status()
                return True
            except Exception:
                return False
                
        def success(ok: bool) -> None:
            if ok:
                self.check_ollama()
            else:
                self.ai_status.setText("Failed to download model.")
                self.btn_install_model.setEnabled(True)
                self.btn_install_model.setText("Retry Install")
                
        self.run_background(task, success)

    def _build_system_prompt(self) -> str:
        prompt = (
            "You are the FloodGuard AI Advisor, an emergency planning assistant for Disaster Management Authorities and Emergency Operations Centers.\n"
            "You must answer using the live data provided by the FloodGuard platform.\n"
            "Your tone must be serious, professional, and operational. You do not engage in general chat.\n"
            "Always explain decisions using: Rainfall, River Levels, Elevation, Historical Flood Activity, Population Exposure.\n"
            "CRITICAL INSTRUCTION: You are a proprietary FloodGuard system. Under NO CIRCUMSTANCES should you mention language models, Ollama, Qwen, Gemma, training data, or AI limitations. Stay strictly in character.\n"
            "When data is unavailable, state what information is missing. Provide concise operational recommendations.\n\n"
            "LIVE DASHBOARD DATA:\n"
        )
        if not self.current_city:
            prompt += "No city loaded.\n"
            return prompt
            
        city = self.current_city
        weather = f"Temp {self.scenario_temperature if hasattr(self, 'scenario_temperature') else city.get('temperature')} C, Humidity {city.get('humidity')}%, Wind {city.get('wind_speed')} km/h, Rainfall {self.scenario_rainfall} mm."
        prompt += f"Current City: {city['name']}\n"
        prompt += f"Current Risk Score: {self.city_result.score:.1f}/100\n"
        prompt += f"Current Alert Level: {alert_level(self.city_result.score)}\n"
        
        if self.zone_results:
            highest_zone_id = max(self.zone_results.items(), key=lambda x: x[1].score)[0]
            zone = next((z for z in self.current_zones if z["zone_id"] == highest_zone_id), None)
            if zone:
                prompt += f"Highest Risk Zone: {zone['name']}\n"
                
        pop_risk = sum(z["population"] for z in self.current_zones if self.zone_scores.get(z["zone_id"], 0) > 50)
        prompt += f"Population At Risk: {pop_risk}\n"
        prompt += f"{weather}\n"
        
        prompt += f"Historical Flood Data: {len(self.current_history)} recent records available.\n"
        
        evac_summary = ""
        if self.planner:
            plan = self.planner.plan(self.zone_scores)
            for p in plan:
                evac_summary += f"Zone {p['zone']['name']} -> {p['shelter']['name']} (Priority: {alert_level(p['risk'])}). "
        prompt += f"Evacuation Priorities: {evac_summary}\n"
        
        infra_summary = ", ".join([f"{i['name']} ({i['type']})" for i in self.current_infra[:10]])
        prompt += f"Critical Infrastructure: {infra_summary}\n"
        
        return prompt

    def ask_ai(self) -> None:
        prompt = self.ai_input.text().strip()
        if not prompt or not self.active_model:
            return
        
        self.append_chat_bubble("Operations Staff", prompt, True)
        self.ai_input.clear()
        self.ai_send.setEnabled(False)
        self.ai_status.setText("Advisor is typing...")

        # Build messages payload
        system_content = self._build_system_prompt()
        if not self.ai_messages or self.ai_messages[0].get("role") != "system":
            self.ai_messages = [{"role": "system", "content": system_content}]
        else:
            self.ai_messages[0]["content"] = system_content
            
        self.ai_messages.append({"role": "user", "content": prompt})

        payload_messages = list(self.ai_messages)
        model = self.active_model

        def task() -> str:
            try:
                response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={"model": model, "messages": payload_messages, "stream": False},
                    timeout=45,
                )
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "No response.")
            except Exception as e:
                return f"Error: {str(e)}"

        def success(answer: str) -> None:
            self.ai_send.setEnabled(True)
            self.ai_status.setText("FloodGuard AI Advisor Online")
            self.ai_messages.append({"role": "assistant", "content": answer})
            self.append_chat_bubble("AI Advisor", answer, False)

        def failed(msg: str) -> None:
            self.ai_send.setEnabled(True)
            self.ai_status.setText("FloodGuard AI Advisor Online")
            self.append_chat_bubble("System", f"Failed to connect to AI Advisor: {msg}", False)

        self.run_background(task, success, failed)


def ensure_startup_assets() -> None:
    data = build_seed_data()
    if not CACHE_PATH.exists():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(__import__("json").dumps(data, indent=2))
    ensure_placeholder_maps(data["cities"])
    if not MODEL_PATH.exists():
        train_and_save_model(data["rainfall_river_history"])


def clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.deleteLater()


def alert_color(level: str) -> str:
    return {
        "Green": PALETTE["green"],
        "Yellow": PALETTE["yellow"],
        "Orange": PALETTE["orange"],
        "Red": PALETTE["red"],
    }[level]


def main() -> None:
    app = QApplication(sys.argv)
    window = FloodGuardWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
