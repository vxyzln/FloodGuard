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

def interpolate_grid(zones, values, lat_min, lat_max, lon_min, lon_max, grid_size=35, power=2.0):
    if not zones or not values:
        return []
        
    lats = np.linspace(lat_min, lat_max, grid_size)
    lons = np.linspace(lon_min, lon_max, grid_size)
    
    zone_coords = np.array([[float(z["latitude"]), float(z["longitude"])] for z in zones])
    zone_vals = np.array(values)
    
    grid_points = []
    for lat in lats:
        for lon in lons:
            # Compute Euclidean distances to all zones
            dists = np.sqrt(np.sum((zone_coords - np.array([lat, lon]))**2, axis=1))
            
            # Check if we are on top of a zone
            zero_dist_idx = np.where(dists < 1e-6)[0]
            if len(zero_dist_idx) > 0:
                val = zone_vals[zero_dist_idx[0]]
            else:
                weights = 1.0 / (dists ** power)
                val = np.sum(weights * zone_vals) / np.sum(weights)
                
            grid_points.append([lat, lon, float(val)])
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
        
        def add_impact_item(layout_obj, label_text, val_lbl):
            lbl = QLabel(label_text)
            lbl.setObjectName("KpiTitle")
            layout_obj.addWidget(lbl)
            layout_obj.addWidget(val_lbl)
            
        add_impact_item(impact_layout, "Predicted Risk Score", self.score_label)
        add_impact_item(impact_layout, "Alert Level", self.alert_badge)
        add_impact_item(impact_layout, "Highest Risk Zone", self.highest_zone_label)
        
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
        self.lbl_map_zone_risk = QLabel("Risk: --")
        self.lbl_map_zone_pop = QLabel("Population: --")
        self.lbl_map_zone_elev = QLabel("Elevation: --")
        self.lbl_map_zone_hist = QLabel("Hist. Flood Events: --")
        self.lbl_map_zone_shelter = QLabel("Nearest Shelter: --")
        
        self.lbl_map_zone_reco = QLabel("Select a zone or click on the map to view details.")
        self.lbl_map_zone_reco.setWordWrap(True)
        self.lbl_map_zone_reco.setStyleSheet("color: #666666; font-size: 13px; line-height: 1.4;")
        
        for lbl in [self.lbl_map_zone_name, self.lbl_map_zone_risk, self.lbl_map_zone_pop, 
                    self.lbl_map_zone_elev, self.lbl_map_zone_hist, self.lbl_map_zone_shelter]:
            lbl.setStyleSheet("font-size: 13px;")
            side_layout.addWidget(lbl)
            
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
            
        nearest_zone = min(
            self.current_zones,
            key=lambda z: distance(lat, lng, float(z["latitude"]), float(z["longitude"]))
        )
        
        nearest_shelter = "None available"
        if self.current_shelters:
            sh = min(
                self.current_shelters,
                key=lambda s: distance(float(nearest_zone["latitude"]), float(nearest_zone["longitude"]), float(s["latitude"]), float(s["longitude"]))
            )
            nearest_shelter = sh["name"]
            
        score = self.zone_scores.get(int(nearest_zone["zone_id"]), 0.0)
        
        if score < 50.0:
            reco = "Safe / Low Risk. Continue monitoring weather updates."
            color = PALETTE["green"]
        elif score < 70.0:
            reco = "Moderate Risk. Advise caution in low-lying areas."
            color = PALETTE["yellow"]
        elif score < 90.0:
            reco = "High Risk. Prepare for evacuation and secure emergency supplies."
            color = PALETTE["orange"]
        else:
            reco = "Severe Risk. Evacuate immediately to the nearest shelter."
            color = PALETTE["red"]
            
        self.lbl_map_zone_name.setText(f"<b>Zone Name:</b> {nearest_zone['name']}")
        self.lbl_map_zone_risk.setText(f"<b>Risk:</b> <font color='{color}'>{score:.1f} / 100</font>")
        self.lbl_map_zone_pop.setText(f"<b>Population:</b> {int(nearest_zone['population']):,}")
        self.lbl_map_zone_elev.setText(f"<b>Elevation:</b> {nearest_zone['elevation_m']} m")
        
        freq = float(nearest_zone.get("historical_flood_frequency") or 0.0)
        self.lbl_map_zone_hist.setText(f"<b>Hist. Flood Events:</b> {int(freq * 10)}")
        self.lbl_map_zone_shelter.setText(f"<b>Nearest Shelter:</b> {nearest_shelter}")
        
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
            return bundle

        self.run_background(task, self.apply_city_data)

    def apply_city_data(self, payload: dict) -> None:
        self.current_city = payload["city"]
        self.current_zones = payload["zones"]
        self.current_shelters = payload["shelters"]
        self.current_infra = payload["infrastructure"]
        self.current_history = payload["history"]
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
            return diff.total_seconds() > 6 * 3600

        # Filter stale cities
        stale_cities = [c for c in cities if is_city_stale(c)]
        if not stale_cities:
            self.set_home_status(self.weather_status_card, "Connected", PALETTE["green"])
            QMessageBox.information(self, "Refresh Complete", "All cached cities are up to date (updated within the last 6 hours).")
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
        if self.city_result.score < 50:
            self.highest_zone_label.setText("Low City Risk")
            self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["green"] + ';')
        elif self.zone_results:
            highest_id, highest = max(self.zone_results.items(), key=lambda item: item[1].score)
            highest_zone = next((zone for zone in self.current_zones if int(zone["zone_id"]) == int(highest_id)), None)
            self.highest_zone_label.setText(highest_zone["name"] if highest_zone else "-")
            self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["text"] + ';')
        else:
            self.highest_zone_label.setText("-")
            self.highest_zone_label.setStyleSheet('font-family: "SF Pro Display"; font-size: 20px; font-weight: bold; color: ' + PALETTE["text"] + ';')
            
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
        
        if self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            
            risk_vals = [self.zone_scores.get(int(z["zone_id"]), 0.0) / 100.0 for z in self.current_zones]
            grid_data = interpolate_grid(self.current_zones, risk_vals, lat_min, lat_max, lon_min, lon_max, grid_size=35)
            
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.35,
                    gradient={0.2: 'green', 0.5: 'yellow', 0.8: 'orange', 1.0: 'red'}
                ).add_to(m)
            
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

        # 1. Population density layer (Heatmap)
        if self.layer_population.isChecked() and self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            
            max_pop = max([float(z["population"]) for z in self.current_zones]) if self.current_zones else 1.0
            span = max_pop if max_pop > 0 else 1.0
            pop_vals = [float(z["population"]) / span for z in self.current_zones]
            grid_data = interpolate_grid(self.current_zones, pop_vals, lat_min, lat_max, lon_min, lon_max, grid_size=35)
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.1,
                    gradient={0.2: 'yellow', 0.6: 'orange', 1.0: 'red'}
                ).add_to(m)
            
        # 2. Flood Risk heatmap layer
        if self.layer_risk.isChecked() and self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            
            risk_vals = [self.zone_scores.get(int(z["zone_id"]), 0.0) / 100.0 for z in self.current_zones]
            grid_data = interpolate_grid(self.current_zones, risk_vals, lat_min, lat_max, lon_min, lon_max, grid_size=35)
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.35,
                    gradient={0.2: 'green', 0.5: 'yellow', 0.8: 'orange', 1.0: 'red'}
                ).add_to(m)
            
        # 3. Elevation heatmap layer
        if self.layer_elevation.isChecked() and self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            
            elevations = [float(z["elevation_m"]) for z in self.current_zones]
            min_elev = min(elevations) if elevations else 0.0
            max_elev = max(elevations) if elevations else 1.0
            span = max_elev - min_elev if max_elev > min_elev else 1.0
            
            elev_vals = [0.15 + 0.85 * ((max_elev - float(z["elevation_m"])) / span) for z in self.current_zones]
            grid_data = interpolate_grid(self.current_zones, elev_vals, lat_min, lat_max, lon_min, lon_max, grid_size=35)
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.4,
                    gradient={0.15: 'green', 0.55: 'orange', 1.0: 'red'}
                ).add_to(m)
            
        # 4. Historical flood extent layer
        if self.layer_history.isChecked() and self.current_zones:
            lats = [float(z["latitude"]) for z in self.current_zones]
            lons = [float(z["longitude"]) for z in self.current_zones]
            lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
            lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            
            freqs = [float(z.get("historical_flood_frequency") or 0.0) for z in self.current_zones]
            max_freq = max(freqs) if freqs else 1.0
            span = max_freq if max_freq > 0 else 1.0
            
            freq_vals = [float(z.get("historical_flood_frequency") or 0.0) / span for z in self.current_zones]
            grid_data = interpolate_grid(self.current_zones, freq_vals, lat_min, lat_max, lon_min, lon_max, grid_size=35)
            if grid_data:
                folium.plugins.HeatMap(
                    grid_data,
                    radius=35,
                    blur=25,
                    min_opacity=0.25,
                    gradient={0.2: '#93C5FD', 0.6: '#3B82F6', 1.0: '#1D4ED8'}
                ).add_to(m)
                    
        # 5. Critical infrastructure layer
        if self.layer_infra.isChecked() and self.current_infra:
            for inf in self.current_infra:
                zone = next((z for z in self.current_zones if z["zone_id"] == inf["zone_id"]), None)
                elevation = zone["elevation_m"] if zone else city["elevation"]
                score = self.zone_scores.get(int(inf["zone_id"]), 0.0) if zone else 0.0
                risk_lvl = alert_level(score)
                
                # Determine status
                if score >= 90.0:
                    status = "Critical Alert"
                elif score >= 70.0:
                    status = "Under Alert"
                else:
                    status = "Operational"
                    
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
                    
                nearest_s = min(self.current_shelters, key=lambda s: get_distance(float(inf["latitude"]), float(inf["longitude"]), float(s["latitude"]), float(s["longitude"]))) if self.current_shelters else None
                nearest_s_name = nearest_s["name"] if nearest_s else "None"
                
                popup_content = f"""
                <div style="font-family: 'SF Pro Text', sans-serif; font-size:12px; line-height: 1.4; width: 220px;">
                    <b>Name:</b> {inf['name']}<br>
                    <b>Type:</b> {inf['type'].title()}<br>
                    <b>Elevation:</b> {int(elevation)} m<br>
                    <b>Risk Level:</b> {risk_lvl}<br>
                    <b>Nearest Shelter:</b> {nearest_s_name}<br>
                    <b>Status:</b> {status}
                </div>
                """
                
                folium.Marker(
                    location=[inf["latitude"], inf["longitude"]],
                    icon=folium.Icon(color=color, icon=icon_name),
                    popup=folium.Popup(popup_content, max_width=250)
                ).add_to(m)
                
        # 6. Evacuation Points layer
        if self.layer_evac.isChecked() and self.current_shelters:
            for idx, s in enumerate(self.current_shelters):
                types = ["Shelter", "Assembly Point", "Emergency Camp", "Rescue Base"]
                e_type = types[idx % len(types)]
                
                nearest_z = min(self.current_zones, key=lambda z: get_distance(float(s["latitude"]), float(s["longitude"]), float(z["latitude"]), float(z["longitude"]))) if self.current_zones else None
                elevation = nearest_z["elevation_m"] if nearest_z else city["elevation"]
                score = self.zone_scores.get(int(nearest_z["zone_id"]), 0.0) if nearest_z else 0.0
                risk_lvl = alert_level(score)
                
                status = "Active" if score < 90 else "Inaccessible"
                
                if e_type == "Shelter":
                    color = "green"
                    icon_name = "home"
                elif e_type == "Assembly Point":
                    color = "orange"
                    icon_name = "flag"
                elif e_type == "Emergency Camp":
                    color = "cadetblue"
                    icon_name = "fire"
                else:
                    color = "purple"
                    icon_name = "star"
                    
                nearest_other_s = min([other_s for other_s in self.current_shelters if other_s["shelter_id"] != s["shelter_id"]], key=lambda os: get_distance(float(s["latitude"]), float(s["longitude"]), float(os["latitude"]), float(os["longitude"]))) if len(self.current_shelters) > 1 else None
                nearest_s_name = nearest_other_s["name"] if nearest_other_s else "N/A (Self)"
                
                popup_content = f"""
                <div style="font-family: 'SF Pro Text', sans-serif; font-size:12px; line-height: 1.4; width: 220px;">
                    <b>Name:</b> {s['name']}<br>
                    <b>Type:</b> {e_type}<br>
                    <b>Elevation:</b> {int(elevation)} m<br>
                    <b>Risk Level:</b> {risk_lvl}<br>
                    <b>Nearest Shelter:</b> {nearest_s_name}<br>
                    <b>Status:</b> {status}
                </div>
                """
                
                folium.Marker(
                    location=[s["latitude"], s["longitude"]],
                    icon=folium.Icon(color=color, icon=icon_name),
                    popup=folium.Popup(popup_content, max_width=250)
                ).add_to(m)
                
        # Dynamic Legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 20px; left: 20px; width: 220px; height: auto; 
                    background-color: white; border: 2px solid #D6D3D1; z-index:9999; font-size:12px;
                    padding: 10px; border-radius: 8px; font-family: sans-serif; opacity: 0.95; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <b style="font-size:13px; color:#111827;">Map Legend</b><br>
        '''
        
        has_legend_content = False
        if self.layer_risk.isChecked():
            has_legend_content = True
            legend_html += f'''
            <div style="margin-top: 6px; color:#111827;">
                <b>Flood Risk</b><br>
                <i style="background: {PALETTE['green']}; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Safe<br>
                <i style="background: {PALETTE['yellow']}; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Moderate<br>
                <i style="background: {PALETTE['orange']}; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> High<br>
                <i style="background: {PALETTE['red']}; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Severe<br>
            </div>
            '''
            
        if self.layer_elevation.isChecked():
            has_legend_content = True
            legend_html += '''
            <div style="margin-top: 6px; color:#111827;">
                <b>Elevation</b><br>
                <i style="background: green; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> High<br>
                <i style="background: orange; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Medium<br>
                <i style="background: red; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Low<br>
            </div>
            '''
            
        if self.layer_population.isChecked():
            has_legend_content = True
            legend_html += '''
            <div style="margin-top: 6px; color:#111827;">
                <b>Population Density</b><br>
                <i style="background: red; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> High Density<br>
                <i style="background: orange; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Medium Density<br>
                <i style="background: yellow; width: 12px; height: 12px; float: left; margin-right: 5px; border-radius: 2px;"></i> Low Density<br>
            </div>
            '''
            
        legend_html += '</div>'
        
        if has_legend_content:
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
