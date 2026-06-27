import sys
from PyQt6.QtWidgets import QApplication
from app import FloodGuardWindow
import time

app = QApplication(sys.argv)
window = FloodGuardWindow()

print("Waiting for Ollama check...")
while "Checking connection" in window.ai_status.text():
    app.processEvents()
    time.sleep(0.1)

print(f"Ollama status: {window.ai_status.text()}")
if "Offline" in window.ai_status.text():
    print("AI Advisor is offline. Exiting.")
    sys.exit(0)

print("Loading Mumbai...")
window.load_city("Mumbai")
while window.current_city is None or window.current_city["name"] != "Mumbai":
    app.processEvents()
    time.sleep(0.1)

print("Testing AI Advisor Presets...")
window.ask_ai_preset("risk")
# Wait for the AI to start typing
while "typing" not in window.ai_status.text():
    app.processEvents()
    time.sleep(0.1)

# Wait for the AI to finish
while not window.ai_send.isEnabled():
    app.processEvents()
    time.sleep(0.1)

print("AI Chat Output:")
print(window.ai_chat.toPlainText())

sys.exit(0)

 
