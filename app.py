from __future__ import annotations

from datetime import datetime
import sys

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
)

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.image as mpimg
import requests

from floodguard.config import CACHE_PATH, MODEL_PATH, PALETTE, ROOT
from floodguard.evacuation import EvacuationPlanner
from floodguard.map_assets import ensure_placeholder_maps
from floodguard.risk_model import RiskResult, train_and_save_model
from floodguard.seed_definitions import alert_level, build_seed_data
from floodguard.city_service import CityService
from floodguard.weather_service import WeatherService
from floodguard.cache_service import CacheService
from floodguard.risk_service import RiskService


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
    color: {PALETTE['text']};
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
    background: #FFFFFF;
    color: {PALETTE['text']};
    gridline-color: {PALETTE['border']};
    border: 1px solid {PALETTE['border']};
    font-family: "SF Pro Text", "Helvetica Neue";
}}
QHeaderView::section {{
    background: {PALETTE['panel']};
    color: {PALETTE['text']};
    padding: 6px;
    border: 1px solid {PALETTE['border']};
    font-weight: 600;
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
    background: {PALETTE['border']};
    color: {PALETTE['accent']};
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
    background: {PALETTE['accent']};
    border: 1px solid {PALETTE['accent']};
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
        search_label = QLabel("Search city")
        search_label.setObjectName("HomeSection")
        self.city_search = QLineEdit()
        self.city_search.setObjectName("CitySearch")
        self.city_search.setPlaceholderText("Type a city name")
        self.city_search.textChanged.connect(self.update_search_prompt)
        self.city_search.returnPressed.connect(self.run_city_search)
        self.home_message = QLabel("Press Enter to check city data.")
        self.home_message.setStyleSheet('font-family: "SF Pro Text"; font-size: 15px; color: #666666;')
        self.home_loading = QLabel("")
        self.home_loading.setStyleSheet('font-family: "SF Pro Text"; font-size: 14px; color: #EA580C;')
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.city_search)
        search_layout.addWidget(self.home_message)
        search_layout.addWidget(self.home_loading)
        layout.addWidget(search_wrap)

        self.open_dashboard_button = QPushButton("Open Dashboard")
        self.open_dashboard_button.setObjectName("OpenDashboard")
        self.open_dashboard_button.clicked.connect(self.open_dashboard)
        layout.addWidget(self.open_dashboard_button)

        # Status row below Search
        status_row = QHBoxLayout()
        status_row.setSpacing(18)
        self.database_status_card = self.home_status_card("Database Status", "Checking", "#EA580C")
        self.weather_status_card = self.home_status_card("Weather API Status", "Standby", "#EA580C")
        self.model_status_card = self.home_status_card("Risk Model Status", "Checking", "#EA580C")
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

        main = QHBoxLayout()
        main.setSpacing(18)
        map_card = QFrame()
        map_card.setObjectName("DashboardCard")
        map_layout = QVBoxLayout(map_card)
        map_layout.setContentsMargins(18, 18, 18, 18)
        map_layout.setSpacing(10)
        self.dashboard_map_canvas = MplCanvas()
        self.dashboard_map_canvas.mpl_connect("button_press_event", self.handle_dashboard_map_click)
        self.dashboard_zone_summary = QLabel("Select a zone on the map")
        self.dashboard_zone_summary.setObjectName("DashboardMeta")
        map_layout.addWidget(self.dashboard_map_canvas, 1)
        map_layout.addWidget(self.dashboard_zone_summary)
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
        self.score_label.setStyleSheet('font-family: "SF Mono", "Menlo"; font-size: 48px; font-weight: bold;')
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
        self.rainfall_value = QLabel()
        self.river_value = QLabel()
        self.rainfall_slider.valueChanged.connect(self.update_from_sliders)
        self.river_slider.valueChanged.connect(self.update_from_sliders)
        
        rain_label = QLabel("Rainfall Scenario")
        river_label = QLabel("River Level Scenario")
        self.reset_scenario_btn = QPushButton("Reset Scenario")
        self.reset_scenario_btn.clicked.connect(self.reset_scenario)
        self.reset_scenario_btn.setStyleSheet(f"QPushButton {{ background-color: {PALETTE['accent']}; color: #FFFFFF; font-weight: bold; padding: 8px 14px; border-radius: 6px; }} QPushButton:hover {{ background-color: {PALETTE['accent_hover']}; }}")
        
        for label in [rain_label, river_label, self.rainfall_value, self.river_value]:
            label.setObjectName("DashboardMeta")
            
        control_layout.addWidget(control_title, 0, 0, 1, 7)
        control_layout.addWidget(rain_label, 1, 0)
        control_layout.addWidget(self.rainfall_slider, 1, 1)
        control_layout.addWidget(self.rainfall_value, 1, 2)
        control_layout.addWidget(river_label, 1, 3)
        control_layout.addWidget(self.river_slider, 1, 4)
        control_layout.addWidget(self.river_value, 1, 5)
        control_layout.addWidget(self.reset_scenario_btn, 1, 6)
        
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
        
        self.map_canvas = MplCanvas()
        self.map_canvas.mpl_connect("button_press_event", self.handle_map_click)
        layout.addWidget(self.map_canvas, 3)
        
        side_card, side_layout = card("Layers")
        side_card.setMinimumWidth(280)
        
        self.layer_infra = QCheckBox("Critical infrastructure")
        self.layer_population = QCheckBox("Population density")
        self.layer_river = QCheckBox("River proximity")
        self.layer_history = QCheckBox("Historical flood extent")
        
        for checkbox in [self.layer_infra, self.layer_population, self.layer_river, self.layer_history]:
            checkbox.setChecked(checkbox in [self.layer_infra, self.layer_population])
            checkbox.stateChanged.connect(self.redraw_map)
            side_layout.addWidget(checkbox)
            
        side_layout.addSpacing(20)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"background-color: {PALETTE['border']}; max-height: 1px; border: 0;")
        side_layout.addWidget(sep)
        
        side_layout.addSpacing(10)
        
        self.zone_detail = QLabel("Click a zone on the map for details.")
        self.zone_detail.setWordWrap(True)
        self.zone_detail.setStyleSheet(f"color: {PALETTE['text']}; font-size: 13px; line-height: 1.4;")
        side_layout.addWidget(self.zone_detail)
        
        side_layout.addStretch()
        layout.addWidget(side_card, 1)
        self.stack.addWidget(page)

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
        self.priority_table = QTableWidget(0, 5)
        self.priority_table.setHorizontalHeaderLabels(["Zone", "Nearest Shelter", "Evacuation Priority", "Teams Required", "Boats Required"])
        plan_layout.addWidget(self.priority_table)
        
        route_card, route_layout = card("Safe Routes View")
        self.route_canvas = MplCanvas()
        route_layout.addWidget(self.route_canvas)
        
        select_layout = QHBoxLayout()
        select_label = QLabel("Highlight route for:")
        select_label.setObjectName("DashboardMeta")
        self.route_select_combo = QComboBox()
        self.route_select_combo.currentTextChanged.connect(lambda: self.redraw_routes(self.planner.plan(self.zone_scores) if self.planner else []))
        select_layout.addWidget(select_label)
        select_layout.addWidget(self.route_select_combo, 1)
        route_layout.addLayout(select_layout)
        
        shelter_card, shelter_layout = card("Shelter Occupancy")
        self.shelter_box = QVBoxLayout()
        shelter_layout.addLayout(self.shelter_box)
        
        grid.addWidget(plan_card, 0, 0, 2, 1)
        grid.addWidget(route_card, 0, 1)
        grid.addWidget(shelter_card, 1, 1)
        layout.addLayout(grid, 1)
        
        self.stack.addWidget(page)

    def build_trends(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)
        
        trend_card, trend_layout = card("Historical Events & Risk Trend")
        self.trend_canvas = MplCanvas()
        trend_layout.addWidget(self.trend_canvas)
        
        analytics_card, analytics_layout = card("Zone Risk Analysis")
        self.analytics_canvas = MplCanvas()
        analytics_layout.addWidget(self.analytics_canvas)
        
        layout.addWidget(trend_card, 1)
        layout.addWidget(analytics_card, 1)
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
                <span style="font-weight: bold; color: {PALETTE['accent']};">{sender}</span>
                <span style="font-size: 11px; color: {PALETTE['muted']}; margin-left: 8px;">{timestamp}</span>
                <div style="margin-top: 6px; white-space: pre-wrap; font-size: 14px;">{message}</div>
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
        self.update_home_status_cards()
        self.update_search_prompt()
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
        
        self.rainfall_slider.blockSignals(True)
        self.river_slider.blockSignals(True)
        self.rainfall_slider.setValue(0)
        self.river_slider.setValue(0)
        self.rainfall_slider.blockSignals(False)
        self.river_slider.blockSignals(False)

    def fetch_weather_if_online(self) -> None:
        self.using_cached = False
        if not self.online_mode:
            if hasattr(self, "weather_status_card"):
                self.set_home_status(self.weather_status_card, "Standby", "#EA580C")
            return
        if hasattr(self, "home_loading"):
            self.home_loading.setText("Updating weather...")
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Updating weather...")

        city_id = int(self.current_city["city_id"])
        lat = float(self.current_city["latitude"])
        lon = float(self.current_city["longitude"])

        def task() -> dict:
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
                self.set_home_status(self.weather_status_card, "Ready", "#16A34A")
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            if hasattr(self, "dashboard_status"):
                self.dashboard_status.setText("")
            self.update_dashboard()

        def failed(message: str) -> None:
            self.using_cached = True
            if hasattr(self, "weather_status_card"):
                self.set_home_status(self.weather_status_card, "Stored Data", "#EA580C")
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            if hasattr(self, "dashboard_status"):
                self.dashboard_status.setText("Using stored data")

        self.run_background(task, success, failed)

    def update_from_sliders(self) -> None:
        if not self.current_zones:
            return
        rain_pct = float(self.rainfall_slider.value())
        river_pct = float(self.river_slider.value())
        
        if self.real_rainfall > 0.0:
            self.scenario_rainfall = max(0.0, self.real_rainfall * (1.0 + rain_pct / 100.0))
        else:
            self.scenario_rainfall = max(0.0, (rain_pct / 100.0) * 100.0) if rain_pct > 0 else 0.0
            
        if self.real_river_level > 0.0:
            self.scenario_river_level = max(0.0, self.real_river_level * (1.0 + river_pct / 100.0))
        else:
            self.scenario_river_level = max(0.0, (river_pct / 100.0) * 5.0) if river_pct > 0 else 0.0
            
        rain_sign = "+" if rain_pct >= 0 else ""
        river_sign = "+" if river_pct >= 0 else ""
        self.rainfall_value.setText(f"{self.scenario_rainfall:.1f} mm ({rain_sign}{rain_pct:.0f}%)")
        self.river_value.setText(f"{self.scenario_river_level:.1f} m ({river_sign}{river_pct:.0f}%)")
        
        self.risk_request_id += 1
        request_id = self.risk_request_id
        zones = [dict(zone) for zone in self.current_zones]
        history = [dict(row) for row in self.current_history]
        city_id = int(self.current_city["city_id"])
        mode = "online" if self.online_mode and not self.using_cached else "offline"
        if hasattr(self, "dashboard_status"):
            self.dashboard_status.setText("Updating scenario...")

        def task() -> dict:
            res = self.risk_service.score_scenario(self.scenario_rainfall, self.scenario_river_level, zones, history)
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
        self.rainfall_slider.blockSignals(True)
        self.river_slider.blockSignals(True)
        self.rainfall_slider.setValue(0)
        self.river_slider.setValue(0)
        self.rainfall_slider.blockSignals(False)
        self.river_slider.blockSignals(False)
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
        self.update_dashboard()
        if self.stack.currentIndex() == 2:
            self.redraw_map()
        if self.stack.currentIndex() == 3:
            self.refresh_evacuation()

    def update_dashboard(self) -> None:
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
        self.score_label.setText(f"{self.city_result.score:.0f}")
        self.alert_badge.setText(level)
        badge_text_color = "#111111" if level in {"Green", "Yellow"} else "#FFFFFF"
        self.alert_badge.setStyleSheet(
            f"background: {color}; color: {badge_text_color}; border-radius: 12px; padding: 10px 14px; "
            'font-family: "SF Pro Display"; font-size: 28px; font-weight: bold;'
        )
        if self.zone_results:
            highest_id, highest = max(self.zone_results.items(), key=lambda item: item[1].score)
            highest_zone = next((zone for zone in self.current_zones if int(zone["zone_id"]) == int(highest_id)), None)
            self.highest_zone_label.setText(highest_zone["name"] if highest_zone else "-")
        else:
            self.highest_zone_label.setText("-")
            
        self.real_rain_label.setText(f"{self.real_rainfall:.1f} mm")
        self.real_river_label.setText(f"{self.real_river_level:.1f} m")
        self.temp_label.setText(f"{self.real_temperature:.1f} °C" if self.real_temperature is not None else "-")
        self.humidity_label.setText(f"{self.real_humidity:.0f}%" if self.real_humidity is not None else "-")
        self.wind_speed_label.setText(f"{self.real_wind_speed:.1f} km/h" if self.real_wind_speed is not None else "-")
        
        self.redraw_dashboard_map()

    def redraw_dashboard_map(self) -> None:
        if not hasattr(self, "dashboard_map_canvas"):
            return
        ax = self.dashboard_map_canvas.axes
        ax.clear()
        city = self.current_city
        if not city:
            return
        extent = [city["map_long_min"], city["map_long_max"], city["map_lat_min"], city["map_lat_max"]]
        image_path = ROOT / city["map_image_path"]
        if image_path.exists():
            ax.imshow(mpimg.imread(image_path), extent=extent, aspect="auto", alpha=0.96)
        ax.set_axis_off()
        ax.set_facecolor(PALETTE["panel"])
        for zone in self.current_zones:
            score = self.zone_scores.get(int(zone["zone_id"]), 0)
            ax.scatter(
                zone["longitude"],
                zone["latitude"],
                s=260,
                color=alert_color(alert_level(score)),
                edgecolor=PALETTE["text"],
                linewidth=2.4,
                zorder=3,
            )
            ax.text(
                zone["longitude"],
                zone["latitude"],
                zone["name"].split()[0],
                color=PALETTE["text"],
                fontsize=9,
                fontweight="bold",
                ha="center",
                va="center",
                zorder=4,
            )
        ax.set_xlim(city["map_long_min"], city["map_long_max"])
        ax.set_ylim(city["map_lat_min"], city["map_lat_max"])
        self.dashboard_map_canvas.draw_idle()

    def handle_dashboard_map_click(self, event) -> None:
        if event.xdata is None or event.ydata is None or not self.current_zones:
            return
        nearest = min(
            self.current_zones,
            key=lambda zone: abs(float(zone["longitude"]) - event.xdata) + abs(float(zone["latitude"]) - event.ydata),
        )
        result = self.zone_results.get(int(nearest["zone_id"]))
        if result:
            self.dashboard_zone_summary.setText(f"{nearest['name']} · {alert_level(result.score)} risk · {result.score:.0f}/100")

    def refresh_all(self) -> None:
        self.refresh_city_combos()
        self.update_from_sliders()
        self.refresh_trends()

    def redraw_map(self) -> None:
        ax = self.map_canvas.axes
        ax.clear()
        city = self.current_city
        if not city:
            return
        extent = [city["map_long_min"], city["map_long_max"], city["map_lat_min"], city["map_lat_max"]]
        image_path = ROOT / city["map_image_path"]
        if image_path.exists():
            ax.imshow(mpimg.imread(image_path), extent=extent, aspect="auto")
        ax.set_facecolor(PALETTE["background"])
        ax.set_title(f"{city['name']} flood risk map", color=PALETTE["text"])
        ax.tick_params(colors=PALETTE["muted"])
        ax.set_xlabel("Longitude", color=PALETTE["muted"])
        ax.set_ylabel("Latitude", color=PALETTE["muted"])
        
        # 1. Population density layer (Heatmap)
        if self.layer_population.isChecked() and self.current_zones:
            import numpy as np
            x = np.linspace(city["map_long_min"], city["map_long_max"], 100)
            y = np.linspace(city["map_lat_min"], city["map_lat_max"], 100)
            X, Y = np.meshgrid(x, y)
            Z = np.zeros_like(X)
            for zone in self.current_zones:
                lat = float(zone["latitude"])
                lon = float(zone["longitude"])
                pop = float(zone["population"])
                sigma = (city["map_long_max"] - city["map_long_min"]) * 0.15
                Z += pop * np.exp(-((X - lon)**2 + (Y - lat)**2) / (2 * sigma**2))
            ax.contourf(X, Y, Z, levels=15, cmap="YlOrRd", alpha=0.45, zorder=1)
            
        # 2. Historical flood extent layer
        if self.layer_history.isChecked() and self.current_zones:
            import numpy as np
            x = np.linspace(city["map_long_min"], city["map_long_max"], 100)
            y = np.linspace(city["map_lat_min"], city["map_lat_max"], 100)
            X, Y = np.meshgrid(x, y)
            Z_flood = np.zeros_like(X)
            for zone in self.current_zones:
                lat = float(zone["latitude"])
                lon = float(zone["longitude"])
                freq = float(zone.get("historical_flood_frequency", 0.3))
                sigma = (city["map_long_max"] - city["map_long_min"]) * 0.12
                Z_flood += freq * np.exp(-((X - lon)**2 + (Y - lat)**2) / (2 * sigma**2))
            ax.contourf(X, Y, Z_flood, levels=[0.1, 0.3, 0.5, 1.0], colors=["#F97316", "#EA580C", "#C2410C"], alpha=0.25, zorder=1)
            
        # 3. River proximity layer
        if self.layer_river.isChecked():
            import numpy as np
            river_x = np.linspace(city["map_long_min"], city["map_long_max"], 200)
            river_y = city["latitude"] + (city["map_lat_max"] - city["map_lat_min"]) * 0.15 * np.sin(
                (river_x - city["longitude"]) * (8 / (city["map_long_max"] - city["map_long_min"]))
            )
            ax.plot(river_x, river_y, color="#3B82F6", linewidth=8, alpha=0.5, zorder=2)
            ax.plot(river_x, river_y, color="#93C5FD", linewidth=24, alpha=0.2, zorder=1)
            
        # 4. Draw zones
        for zone in self.current_zones:
            score = self.zone_scores.get(int(zone["zone_id"]), 0)
            ax.scatter(zone["longitude"], zone["latitude"], s=160, color=alert_color(alert_level(score)), edgecolor="#0B1220", linewidth=1.8, zorder=3)
            ax.text(zone["longitude"], zone["latitude"] + 0.005, zone["name"].split()[0], color=PALETTE["text"], fontsize=8, fontweight="bold", ha="center")
            
        # 5. Critical infrastructure layer
        if self.layer_infra.isChecked():
            for infra in self.current_infra:
                ax.scatter(infra["longitude"], infra["latitude"], marker="^", s=130, color="#EF4444", edgecolor=PALETTE["text"], linewidth=1.2, zorder=4)
                ax.text(infra["longitude"], infra["latitude"] - 0.008, infra["name"], color=PALETTE["text"], fontsize=7, ha="center")
                
        self.map_canvas.draw_idle()

    def handle_map_click(self, event) -> None:
        if event.xdata is None or event.ydata is None:
            return
        nearest = min(
            self.current_zones,
            key=lambda zone: abs(float(zone["longitude"]) - event.xdata) + abs(float(zone["latitude"]) - event.ydata),
        )
        result = self.zone_results.get(int(nearest["zone_id"]))
        if result:
            self.zone_detail.setText(
                f"{nearest['name']}\nRisk: {result.score:.0f} ({alert_level(result.score)})\n"
                f"Population: {nearest['population']:,}\nElevation: {nearest['elevation_m']:.1f} m\n"
                f"Flood frequency: {nearest['historical_flood_frequency']:.2f}"
            )

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
                f"{row['shelter']['name']} ({row['distance_km']:.1f} km)",
                prio_str,
                f"{row['teams']} Teams",
                f"{row['boats']} Boats" if row['boats'] > 0 else "0 Boats",
            ]
            for col, value in enumerate(values):
                self.priority_table.setItem(row_idx, col, QTableWidgetItem(value))
        self.priority_table.resizeColumnsToContents()
        clear_layout(self.shelter_box)
        for shelter in self.current_shelters:
            label = QLabel(f"{shelter['name']} ({shelter['current_occupancy']:,}/{shelter['capacity']:,})")
            label.setStyleSheet("font-family: 'SF Pro Text'; font-size: 13px; font-weight: 500;")
            progress = QProgressBar()
            progress.setMaximum(int(shelter["capacity"]))
            progress.setValue(int(shelter["current_occupancy"]))
            progress.setFormat("%p% occupied")
            progress.setStyleSheet(
                f"QProgressBar {{ background: {PALETTE['surface']}; border: 0; border-radius: 6px; text-align: center; color: {PALETTE['text']}; font-weight: bold; font-family: 'SF Pro Text'; height: 20px; }} "
                f"QProgressBar::chunk {{ background: {PALETTE['accent']}; border-radius: 6px; }}"
            )
            self.shelter_box.addWidget(label)
            self.shelter_box.addWidget(progress)
            
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
        ax = self.route_canvas.axes
        ax.clear()
        city = self.current_city
        if not city:
            return
        ax.set_facecolor(PALETTE["panel"])
        ax.set_title("Evacuation routes map", color=PALETTE["text"])
        for zone in self.current_zones:
            score = self.zone_scores.get(int(zone["zone_id"]), 0)
            ax.scatter(zone["longitude"], zone["latitude"], s=95, color=alert_color(alert_level(score)), zorder=3)
            ax.text(zone["longitude"], zone["latitude"] + 0.005, zone["name"].split()[0], color=PALETTE["text"], fontsize=8, ha="center")
        for shelter in self.current_shelters:
            ax.scatter(shelter["longitude"], shelter["latitude"], marker="s", s=120, color=PALETTE["accent"], zorder=4)
            ax.text(shelter["longitude"], shelter["latitude"] - 0.008, shelter["name"].split()[0], color=PALETTE["text"], fontsize=8, ha="center")
            
        node_lookup = {
            f"zone:{zone['zone_id']}": zone for zone in self.current_zones
        } | {f"shelter:{shelter['shelter_id']}": shelter for shelter in self.current_shelters}
        
        selected = self.route_select_combo.currentText()
        for row in plan:
            if selected != "All Routes" and row["zone"]["name"] != selected:
                continue
            coords = [(node_lookup[node]["longitude"], node_lookup[node]["latitude"]) for node in row["path"] if node in node_lookup]
            if len(coords) >= 2:
                xs, ys = zip(*coords)
                ax.plot(xs, ys, color="#10B981", linewidth=3, alpha=0.85, zorder=2)
                ax.annotate("", xy=coords[-1], xytext=coords[0], arrowprops=dict(arrowstyle="->", color="#10B981", lw=1.5, ls="--"))
                
        ax.set_xlim(city["map_long_min"], city["map_long_max"])
        ax.set_ylim(city["map_lat_min"], city["map_lat_max"])
        ax.tick_params(colors=PALETTE["muted"])
        self.route_canvas.draw_idle()

    def refresh_trends(self) -> None:
        if not hasattr(self, "trend_canvas") or not self.current_city:
            return
        
        city_id = int(self.current_city["city_id"])
        
        def task() -> dict:
            logs = self.cache_service.get_simulation_logs(city_id)
            return {"logs": logs}
            
        def success(payload: dict) -> None:
            logs = payload["logs"]
            
            # 1. Draw historical trends graph
            ax = self.trend_canvas.axes
            ax.clear()
            ax.set_facecolor(PALETTE["panel"])
            ax.set_title("Flood events and recent simulation trend", color=PALETTE["text"])
            
            history = self.current_history
            floods = [idx for idx, row in enumerate(history) if bool(row["flood_occurred"])]
            rain = [float(row["rainfall_mm"]) for row in history]
            ax.plot(rain, color=PALETTE["accent"], label="Rainfall")
            if floods:
                ax.scatter(floods, [rain[idx] for idx in floods], color=PALETTE["red"], label="Flood event")
            if logs:
                risk = [float(row["risk_score"]) for row in reversed([l for l in logs[:20]])]
                ax.plot(range(max(0, len(rain) - len(risk)), len(rain)), risk, color=PALETTE["yellow"], label="Risk log")
            ax.legend(facecolor=PALETTE["panel"], labelcolor=PALETTE["text"])
            ax.tick_params(colors=PALETTE["muted"])
            self.trend_canvas.draw_idle()
            
            # 2. Draw Zone risk analytics bar chart
            if hasattr(self, "analytics_canvas") and self.current_zones:
                ax_zone = self.analytics_canvas.axes
                ax_zone.clear()
                ax_zone.set_facecolor(PALETTE["panel"])
                ax_zone.set_title("Zone-by-Zone Flood Risk Levels", color=PALETTE["text"])
                
                names = [z["name"].split()[0] for z in self.current_zones]
                scores = [self.zone_scores.get(int(z["zone_id"]), 0) for z in self.current_zones]
                colors = [alert_color(alert_level(s)) for s in scores]
                
                bars = ax_zone.bar(names, scores, color=colors, edgecolor=PALETTE["border"], alpha=0.85)
                ax_zone.tick_params(colors=PALETTE["muted"])
                ax_zone.set_ylim(0, 108)
                ax_zone.set_ylabel("Risk Score (0-100)", color=PALETTE["muted"])
                
                for bar in bars:
                    height = bar.get_height()
                    ax_zone.text(
                        bar.get_x() + bar.get_width()/2.,
                        height + 1.5,
                        f"{height:.0f}",
                        ha="center", va="bottom", color=PALETTE["text"], fontsize=8, fontweight="bold"
                    )
                self.analytics_canvas.draw_idle()
                
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
                self.set_home_status(self.database_status_card, "Connected", "#16A34A")
            else:
                self.set_home_status(self.database_status_card, "Disconnected", "#DC2626")
                
            # Weather API
            if self.online_mode:
                self.set_home_status(self.weather_status_card, "Ready", "#16A34A")
            else:
                self.set_home_status(self.weather_status_card, "Cached", "#FACC15")
                
            # Risk Model
            if res["model"]:
                self.set_home_status(self.model_status_card, "Ready", "#16A34A")
            else:
                self.set_home_status(self.model_status_card, "Disconnected", "#DC2626")
                
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
                    self.home_message.setText("✓ Data Ready")
                if hasattr(self, "home_loading"):
                    self.home_loading.setText("✓ Data Ready")
                self.update_cities_list_and_load(city_name, "Data Ready")
                
            elif status == "offline_missing":
                if hasattr(self, "home_message"):
                    self.home_message.setText("✗ City Unavailable Offline")
                if hasattr(self, "home_loading"):
                    self.home_loading.setText("✗ City Unavailable Offline")
                QMessageBox.information(self, "City Not Available", "City Unavailable Offline")
                
            elif status == "downloaded":
                city_name = result["city_name"]
                if hasattr(self, "home_message"):
                    self.home_message.setText("✓ Downloaded and Cached")
                if hasattr(self, "home_loading"):
                    self.home_loading.setText("✓ Downloaded and Cached")
                self.update_cities_list_and_load(city_name, "Downloaded and Cached")
                
        def failed(msg: str) -> None:
            if hasattr(self, "home_loading"):
                self.home_loading.setText("")
            if hasattr(self, "home_message"):
                self.home_message.setText("✗ City search failed")
            QMessageBox.warning(self, "Search Error", f"Failed to search city: {msg}")
            
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
                self.current_city = cities[0]
                self.refresh_city_combos()
                self.load_city(self.current_city["name"])
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
            "You are FloodGuard AI Advisor.\n"
            "You are an expert in: Flood Monitoring, Hydrology, Emergency Management, Disaster Response, Evacuation Planning, Infrastructure Protection, Risk Assessment.\n"
            "You must answer using the live data provided by FloodGuard.\n"
            "Always explain decisions using: Rainfall, River Levels, Elevation, Historical Flood Activity, Population Exposure.\n"
            "Do not mention language models. Do not mention training data. Do not mention AI limitations. Stay focused on flood analysis.\n"
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
