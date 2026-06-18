from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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
from floodguard.repository import FloodRepository
from floodguard.risk_model import FloodRiskModel, RiskResult, city_score, train_and_save_model
from floodguard.seed_definitions import alert_level, build_seed_data
from floodguard.weather import fetch_open_meteo


STYLE = f"""
QMainWindow, QWidget {{
    background: {PALETTE['background']};
    color: {PALETTE['text']};
    font-family: "SF Pro Text", "Helvetica Neue";
    font-size: 13px;
}}
QListWidget {{
    background: {PALETTE['panel']};
    border: 0;
    padding: 10px;
}}
QListWidget::item {{
    padding: 14px 12px;
    border-radius: 8px;
    color: {PALETTE['muted']};
}}
QListWidget::item:selected {{
    background: {PALETTE['accent']};
    color: #07131F;
}}
QFrame#Card {{
    background: {PALETTE['panel']};
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
}}
QPushButton {{
    background: {PALETTE['accent']};
    color: #07131F;
    border: 0;
    padding: 9px 12px;
    border-radius: 8px;
    font-weight: 600;
}}
QPushButton:disabled {{
    background: {PALETTE['border']};
    color: {PALETTE['muted']};
}}
QComboBox, QLineEdit, QTextEdit {{
    background: #102033;
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 8px;
    color: {PALETTE['text']};
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
    background: #102033;
    color: {PALETTE['text']};
    gridline-color: {PALETTE['border']};
    border: 1px solid {PALETTE['border']};
}}
QHeaderView::section {{
    background: {PALETTE['panel']};
    color: {PALETTE['text']};
    padding: 6px;
    border: 1px solid {PALETTE['border']};
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


class FloodGuardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_startup_assets()
        self.repo = FloodRepository()
        ensure_placeholder_maps(self.repo.cities())
        self.model = FloodRiskModel()
        self.online_mode = False
        self.using_cached = False
        self.current_city = self.repo.cities()[0]
        self.current_zones: list[dict] = []
        self.current_shelters: list[dict] = []
        self.current_infra: list[dict] = []
        self.current_history: list[dict] = []
        self.zone_results: dict[int, RiskResult] = {}
        self.zone_scores: dict[int, float] = {}
        self.city_result = RiskResult(0, 0, 0, "Riverine-flood pattern", 0, "", "")
        self.planner: EvacuationPlanner | None = None

        self.setWindowTitle("FloodGuard")
        self.resize(1360, 860)
        self.setStyleSheet(STYLE)
        shell = QWidget()
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        for item in ["⌂  Home", "▣  Dashboard", "◎  Map", "⇢  Evacuation Plan", "↗  Trends & Comparison", "AI  Advisor"]:
            QListWidgetItem(item, self.nav)
        self.nav.currentRowChanged.connect(self.show_screen)
        self.stack = QStackedWidget()
        root.addWidget(self.nav)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.build_home()
        self.build_dashboard()
        self.build_map()
        self.build_evacuation()
        self.build_trends()
        self.build_advisor()
        self.nav.setCurrentRow(0)
        self.load_city(self.current_city["name"])

    def show_screen(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 2:
            self.redraw_map()
        if index == 3:
            self.refresh_evacuation()
        if index == 4:
            self.refresh_trends()

    def build_home(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        header = QLabel("FloodGuard Command Centre")
        header.setStyleSheet('font-family: "SF Pro Display"; font-size: 28px; font-weight: 600;')
        layout.addWidget(header)
        status_card, status_layout = card("Operations")
        self.mode_toggle = QCheckBox("Online mode")
        self.mode_toggle.stateChanged.connect(self.toggle_online)
        self.city_combo = QComboBox()
        self.city_combo.currentTextChanged.connect(self.load_city)
        self.cache_label = QLabel("")
        self.cache_label.setStyleSheet(f"color: {PALETTE['yellow']};")
        status_layout.addWidget(self.mode_toggle)
        status_layout.addWidget(QLabel("City"))
        status_layout.addWidget(self.city_combo)
        status_layout.addWidget(self.cache_label)
        layout.addWidget(status_card)

        add_card, add_layout = card("Add New City")
        form = QFormLayout()
        self.new_city_name = QLineEdit()
        self.new_city_lat = QLineEdit()
        self.new_city_lon = QLineEdit()
        form.addRow("Name", self.new_city_name)
        form.addRow("Latitude", self.new_city_lat)
        form.addRow("Longitude", self.new_city_lon)
        add_layout.addLayout(form)
        self.add_city_button = QPushButton("Add city")
        self.add_city_button.clicked.connect(self.add_new_city)
        add_layout.addWidget(self.add_city_button)
        layout.addWidget(add_card)
        layout.addStretch()
        self.stack.addWidget(page)

    def build_dashboard(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        score_card, score_layout = card("Risk Score")
        self.score_label = QLabel("0")
        self.score_label.setStyleSheet('font-family: "SF Mono", Menlo; font-size: 64px; font-weight: 700;')
        self.confidence_label = QLabel("")
        self.alert_badge = QLabel("Green")
        self.alert_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert_badge.setStyleSheet("border-radius: 8px; padding: 8px; font-weight: 700;")
        score_layout.addWidget(self.score_label)
        score_layout.addWidget(self.confidence_label)
        score_layout.addWidget(self.alert_badge)

        control_card, control_layout = card("Simulation Inputs")
        self.rainfall_slider = QSlider(Qt.Orientation.Horizontal)
        self.rainfall_slider.setRange(0, 160)
        self.river_slider = QSlider(Qt.Orientation.Horizontal)
        self.river_slider.setRange(10, 80)
        self.rainfall_value = QLabel()
        self.river_value = QLabel()
        self.rainfall_slider.valueChanged.connect(self.update_from_sliders)
        self.river_slider.valueChanged.connect(self.update_from_sliders)
        control_layout.addWidget(QLabel("Rainfall mm"))
        control_layout.addWidget(self.rainfall_slider)
        control_layout.addWidget(self.rainfall_value)
        control_layout.addWidget(QLabel("River level m"))
        control_layout.addWidget(self.river_slider)
        control_layout.addWidget(self.river_value)

        explanation_card, explanation_layout = card("Advisor Summary")
        self.pattern_label = QLabel("")
        self.warning_label = QLabel("")
        self.discharge_label = QLabel("")
        self.explanation_label = QLabel("")
        self.explanation_label.setWordWrap(True)
        for widget in [self.pattern_label, self.warning_label, self.discharge_label, self.explanation_label]:
            explanation_layout.addWidget(widget)

        layout.addWidget(score_card, 0, 0)
        layout.addWidget(control_card, 0, 1)
        layout.addWidget(explanation_card, 1, 0, 1, 2)
        self.stack.addWidget(page)

    def build_map(self) -> None:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        map_card, map_layout = card("Risk Map")
        self.map_canvas = MplCanvas()
        self.map_canvas.mpl_connect("button_press_event", self.handle_map_click)
        map_layout.addWidget(self.map_canvas)
        side_card, side_layout = card("Layers")
        self.layer_infra = QCheckBox("Critical infrastructure")
        self.layer_population = QCheckBox("Population density")
        self.layer_river = QCheckBox("River proximity")
        self.layer_history = QCheckBox("Historical flood extent")
        for checkbox in [self.layer_infra, self.layer_population, self.layer_river, self.layer_history]:
            checkbox.setChecked(checkbox in [self.layer_infra, self.layer_population])
            checkbox.stateChanged.connect(self.redraw_map)
            side_layout.addWidget(checkbox)
        self.zone_detail = QLabel("Click a zone for details.")
        self.zone_detail.setWordWrap(True)
        side_layout.addWidget(self.zone_detail)
        side_layout.addStretch()
        layout.addWidget(map_card, 3)
        layout.addWidget(side_card, 1)
        self.stack.addWidget(page)

    def build_evacuation(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        plan_card, plan_layout = card("Priority Ranking")
        self.priority_table = QTableWidget(0, 7)
        self.priority_table.setHorizontalHeaderLabels(["Zone", "Risk", "Shelter", "Distance", "Priority", "Teams", "Boats"])
        plan_layout.addWidget(self.priority_table)
        route_card, route_layout = card("Routes")
        self.route_canvas = MplCanvas()
        route_layout.addWidget(self.route_canvas)
        self.block_combo = QComboBox()
        self.block_button = QPushButton("Block selected road")
        self.block_button.clicked.connect(self.block_selected_road)
        route_layout.addWidget(self.block_combo)
        route_layout.addWidget(self.block_button)
        shelter_card, shelter_layout = card("Shelter Capacity")
        self.shelter_box = QVBoxLayout()
        shelter_layout.addLayout(self.shelter_box)
        layout.addWidget(plan_card, 0, 0, 2, 1)
        layout.addWidget(route_card, 0, 1)
        layout.addWidget(shelter_card, 1, 1)
        self.stack.addWidget(page)

    def build_trends(self) -> None:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        trend_card, trend_layout = card("Historical Events & Risk Trend")
        self.trend_canvas = MplCanvas()
        trend_layout.addWidget(self.trend_canvas)
        compare_card, compare_layout = card("Two-City Comparison")
        self.compare_combo = QComboBox()
        self.compare_combo.currentTextChanged.connect(self.refresh_trends)
        self.compare_label = QLabel("")
        self.compare_label.setWordWrap(True)
        compare_layout.addWidget(self.compare_combo)
        compare_layout.addWidget(self.compare_label)
        layout.addWidget(trend_card, 0, 0, 1, 2)
        layout.addWidget(compare_card, 1, 0, 1, 2)
        self.stack.addWidget(page)

    def build_advisor(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        ai_card, ai_layout = card("AI Advisor")
        self.ai_status = QLabel("Local AI advisor not checked yet.")
        self.ai_chat = QTextEdit()
        self.ai_input = QLineEdit()
        self.ai_send = QPushButton("Send")
        self.ai_send.clicked.connect(self.ask_ai)
        ai_layout.addWidget(self.ai_status)
        ai_layout.addWidget(self.ai_chat)
        ai_layout.addWidget(self.ai_input)
        ai_layout.addWidget(self.ai_send)
        layout.addWidget(ai_card)
        self.stack.addWidget(page)
        self.check_ollama()

    def toggle_online(self) -> None:
        self.online_mode = self.mode_toggle.isChecked()
        self.add_city_button.setEnabled(self.online_mode)
        self.fetch_weather_if_online()
        self.update_from_sliders()

    def load_city(self, name: str) -> None:
        if not name:
            return
        city = self.repo.city_by_name(name)
        if not city:
            return
        self.current_city = city
        self.current_zones = self.repo.zones(int(city["city_id"]))
        self.current_shelters = self.repo.shelters(int(city["city_id"]))
        self.current_infra = self.repo.infrastructure(int(city["city_id"]))
        self.current_history = self.repo.history(int(city["city_id"]))
        self.planner = EvacuationPlanner(self.current_zones, self.current_shelters)
        self.fetch_weather_if_online()
        self.set_default_sliders()
        self.refresh_all()

    def refresh_city_combos(self) -> None:
        current = self.current_city["name"] if self.current_city else ""
        for combo in [self.city_combo, self.compare_combo]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([city["name"] for city in self.repo.cities()])
            if current:
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def set_default_sliders(self) -> None:
        if not self.current_history:
            self.rainfall_slider.setValue(30)
            self.river_slider.setValue(35)
            return
        recent = self.current_history[-1]
        self.rainfall_slider.blockSignals(True)
        self.river_slider.blockSignals(True)
        self.rainfall_slider.setValue(int(float(recent["rainfall_mm"])))
        self.river_slider.setValue(int(float(recent["river_level_m"]) * 10))
        self.rainfall_slider.blockSignals(False)
        self.river_slider.blockSignals(False)

    def fetch_weather_if_online(self) -> None:
        self.using_cached = False
        if not self.online_mode:
            self.cache_label.setText("Offline mode: local cached data only.")
            return
        try:
            payload = fetch_open_meteo(float(self.current_city["latitude"]), float(self.current_city["longitude"]))
            rainfall = min(160, int(payload["rainfall_mm"]))
            self.rainfall_slider.setValue(rainfall)
            self.cache_label.setText("Online mode: live weather loaded.")
        except Exception:
            self.using_cached = True
            self.cache_label.setText("Using cached data.")

    def update_from_sliders(self) -> None:
        if not self.current_zones:
            return
        rainfall = float(self.rainfall_slider.value())
        river = float(self.river_slider.value()) / 10
        self.rainfall_value.setText(f"{rainfall:.0f} mm")
        self.river_value.setText(f"{river:.1f} m")
        recent_rain = [float(row["rainfall_mm"]) for row in self.current_history[-10:]] + [rainfall]
        recent_river = [float(row["river_level_m"]) for row in self.current_history[-10:]] + [river]
        self.zone_results = {
            int(zone["zone_id"]): self.model.score_zone(rainfall, river, zone, recent_rain, recent_river)
            for zone in self.current_zones
        }
        self.zone_scores = {zone_id: result.score for zone_id, result in self.zone_results.items()}
        self.city_result = city_score(self.zone_results)
        self.update_dashboard()
        self.repo.log_simulation(
            int(self.current_city["city_id"]),
            rainfall,
            river,
            self.city_result.score,
            self.city_result.confidence_low,
            self.city_result.confidence_high,
            "online" if self.online_mode and not self.using_cached else "offline",
            self.city_result.explanation,
        )
        if self.stack.currentIndex() == 2:
            self.redraw_map()
        if self.stack.currentIndex() == 3:
            self.refresh_evacuation()

    def update_dashboard(self) -> None:
        level = alert_level(self.city_result.score)
        color = alert_color(level)
        self.score_label.setText(f"{self.city_result.score:.0f}")
        self.confidence_label.setText(f"Confidence band {self.city_result.confidence_low:.0f}-{self.city_result.confidence_high:.0f}")
        self.alert_badge.setText(level)
        self.alert_badge.setStyleSheet(f"background: {color}; color: #07131F; border-radius: 8px; padding: 8px; font-weight: 700;")
        self.pattern_label.setText(self.city_result.pattern)
        self.warning_label.setText(self.city_result.rainfall_warning)
        self.discharge_label.setText(f"River discharge trend: {self.city_result.discharge_rate:+.2f} m/step")
        self.explanation_label.setText(self.city_result.explanation)

    def refresh_all(self) -> None:
        self.refresh_city_combos()
        self.update_from_sliders()
        self.redraw_map()
        self.refresh_evacuation()
        self.refresh_trends()

    def redraw_map(self) -> None:
        ax = self.map_canvas.axes
        ax.clear()
        city = self.current_city
        extent = [city["map_long_min"], city["map_long_max"], city["map_lat_min"], city["map_lat_max"]]
        image_path = ROOT / city["map_image_path"]
        if image_path.exists():
            ax.imshow(mpimg.imread(image_path), extent=extent, aspect="auto")
        ax.set_facecolor(PALETTE["background"])
        ax.set_title(f"{city['name']} flood risk map", color=PALETTE["text"])
        ax.tick_params(colors=PALETTE["muted"])
        ax.set_xlabel("Longitude", color=PALETTE["muted"])
        ax.set_ylabel("Latitude", color=PALETTE["muted"])
        if self.layer_history.isChecked():
            ax.fill_between(
                [city["map_long_min"], city["map_long_max"]],
                city["map_lat_min"],
                (city["map_lat_min"] + city["map_lat_max"]) / 2,
                color=PALETTE["orange"],
                alpha=0.13,
            )
        if self.layer_river.isChecked():
            ax.plot(
                [city["map_long_min"] + 0.03, city["map_long_max"] - 0.03],
                [city["map_lat_min"] + 0.05, city["map_lat_max"] - 0.06],
                color="#5BA7C8",
                linewidth=7,
                alpha=0.65,
            )
        for zone in self.current_zones:
            score = self.zone_scores.get(int(zone["zone_id"]), 0)
            size = 70 + int(zone["population"]) / 900 if self.layer_population.isChecked() else 160
            ax.scatter(zone["longitude"], zone["latitude"], s=size, color=alert_color(alert_level(score)), edgecolor="#0B1220", linewidth=1.8)
            ax.text(zone["longitude"], zone["latitude"], zone["name"].split()[0], color=PALETTE["text"], fontsize=8)
        if self.layer_infra.isChecked():
            for infra in self.current_infra:
                ax.scatter(infra["longitude"], infra["latitude"], marker="^", s=120, color=PALETTE["accent"], edgecolor="#07131F")
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
        self.priority_table.setRowCount(len(plan))
        for row_idx, row in enumerate(plan):
            values = [
                row["zone"]["name"],
                f"{row['risk']:.0f}",
                row["shelter"]["name"],
                f"{row['distance_km']:.1f} km",
                f"{row['priority_score']:.0f}",
                str(row["teams"]),
                str(row["boats"]),
            ]
            for col, value in enumerate(values):
                self.priority_table.setItem(row_idx, col, QTableWidgetItem(value))
        self.priority_table.resizeColumnsToContents()
        clear_layout(self.shelter_box)
        for shelter in self.current_shelters:
            label = QLabel(f"{shelter['name']} ({shelter['current_occupancy']:,}/{shelter['capacity']:,})")
            progress = QProgressBar()
            progress.setMaximum(int(shelter["capacity"]))
            progress.setValue(int(shelter["current_occupancy"]))
            progress.setFormat("%p% occupied")
            self.shelter_box.addWidget(label)
            self.shelter_box.addWidget(progress)
        self.block_combo.blockSignals(True)
        self.block_combo.clear()
        self.block_combo.addItems(self.planner.available_edge_labels())
        self.block_combo.blockSignals(False)
        self.redraw_routes(plan)

    def redraw_routes(self, plan: list[dict]) -> None:
        ax = self.route_canvas.axes
        ax.clear()
        city = self.current_city
        ax.set_facecolor(PALETTE["panel"])
        ax.set_title("Shortest safe routes", color=PALETTE["text"])
        for zone in self.current_zones:
            ax.scatter(zone["longitude"], zone["latitude"], s=95, color=alert_color(alert_level(self.zone_scores.get(int(zone["zone_id"]), 0))))
        for shelter in self.current_shelters:
            ax.scatter(shelter["longitude"], shelter["latitude"], marker="s", s=120, color=PALETTE["accent"])
        node_lookup = {
            f"zone:{zone['zone_id']}": zone for zone in self.current_zones
        } | {f"shelter:{shelter['shelter_id']}": shelter for shelter in self.current_shelters}
        for row in plan[:4]:
            coords = [(node_lookup[node]["longitude"], node_lookup[node]["latitude"]) for node in row["path"] if node in node_lookup]
            if len(coords) >= 2:
                xs, ys = zip(*coords)
                ax.plot(xs, ys, color=PALETTE["accent"], linewidth=2, alpha=0.8)
        ax.set_xlim(city["map_long_min"], city["map_long_max"])
        ax.set_ylim(city["map_lat_min"], city["map_lat_max"])
        ax.tick_params(colors=PALETTE["muted"])
        self.route_canvas.draw_idle()

    def block_selected_road(self) -> None:
        if self.planner:
            self.planner.block_edge(self.block_combo.currentText())
            self.refresh_evacuation()

    def refresh_trends(self) -> None:
        if not hasattr(self, "trend_canvas"):
            return
        history = self.current_history
        logs = self.repo.simulation_logs(int(self.current_city["city_id"]))
        ax = self.trend_canvas.axes
        ax.clear()
        ax.set_facecolor(PALETTE["panel"])
        ax.set_title("Flood events and recent simulation trend", color=PALETTE["text"])
        floods = [idx for idx, row in enumerate(history) if bool(row["flood_occurred"])]
        rain = [float(row["rainfall_mm"]) for row in history]
        ax.plot(rain, color=PALETTE["accent"], label="Rainfall")
        if floods:
            ax.scatter(floods, [rain[idx] for idx in floods], color=PALETTE["red"], label="Flood event")
        if logs:
            risk = [float(row["risk_score"]) for row in reversed(logs[-20:])]
            ax.plot(range(max(0, len(rain) - len(risk)), len(rain)), risk, color=PALETTE["yellow"], label="Risk log")
        ax.legend(facecolor=PALETTE["panel"], labelcolor=PALETTE["text"])
        ax.tick_params(colors=PALETTE["muted"])
        self.trend_canvas.draw_idle()
        other = self.repo.city_by_name(self.compare_combo.currentText()) if hasattr(self, "compare_combo") else None
        if other:
            other_history = self.repo.history(int(other["city_id"]))
            avg_rain = sum(float(row["rainfall_mm"]) for row in other_history[-14:]) / max(1, len(other_history[-14:]))
            avg_here = sum(float(row["rainfall_mm"]) for row in history[-14:]) / max(1, len(history[-14:]))
            self.compare_label.setText(
                f"{self.current_city['name']}: current risk {self.city_result.score:.0f}, 14-day rainfall avg {avg_here:.1f} mm\n"
                f"{other['name']}: 14-day rainfall avg {avg_rain:.1f} mm\n"
                "# TODO: expand comparison with normalized multi-city risk model outputs."
            )

    def add_new_city(self) -> None:
        if not self.online_mode:
            return
        try:
            city = self.repo.add_city(self.new_city_name.text().strip(), float(self.new_city_lat.text()), float(self.new_city_lon.text()))
            ensure_placeholder_maps([city])
            self.current_city = city
            self.refresh_city_combos()
            self.city_combo.setCurrentText(city["name"])
        except Exception as exc:
            QMessageBox.warning(self, "Add city failed", f"Enter a valid name, latitude and longitude.\n{exc}")

    def check_ollama(self) -> None:
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=1.5)
            response.raise_for_status()
            self.ai_status.setText("Local AI advisor available.")
            self.ai_send.setEnabled(True)
        except Exception:
            self.ai_status.setText("Local AI advisor not available - install Ollama to enable this feature.")
            self.ai_send.setEnabled(False)

    def ask_ai(self) -> None:
        prompt = self.ai_input.text().strip()
        if not prompt:
            return
        context = f"City: {self.current_city['name']}. Risk: {self.city_result.score:.0f}. Alert: {alert_level(self.city_result.score)}."
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2", "prompt": f"{context}\nEmergency planning question: {prompt}", "stream": False},
                timeout=8,
            )
            response.raise_for_status()
            answer = response.json().get("response", "No response.")
        except Exception:
            answer = "Local AI advisor not available - install Ollama to enable this feature."
        self.ai_chat.append(f"Planner: {prompt}\nAdvisor: {answer}\n")
        self.ai_input.clear()


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

