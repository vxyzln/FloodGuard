import re

with open("app.py", "r") as f:
    content = f.read()

# 1. Add timer to __init__
init_patch = '''        self.scenario_river_level = 0.0
        self.active_model: str | None = None
        self.slider_timer = QTimer(self)
        self.slider_timer.setSingleShot(True)
        self.slider_timer.timeout.connect(self.run_update_from_sliders)'''
content = content.replace("        self.scenario_river_level = 0.0\n        self.active_model: str | None = None", init_patch)

# 2. Rename update_from_sliders to run_update_from_sliders, and create a new update_from_sliders that just starts the timer
update_patch = '''    def update_from_sliders(self) -> None:
        self.slider_timer.start(250)

    def run_update_from_sliders(self) -> None:'''
content = content.replace("    def update_from_sliders(self) -> None:", update_patch)

with open("app.py", "w") as f:
    f.write(content)
print("Patched debounce!")
