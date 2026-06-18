import re

with open("app.py", "r") as f:
    content = f.read()

# Restore #FFFFFF on primary buttons
# E.g. QPushButton { background: {PALETTE['accent']}; color: {PALETTE['text']}; ...
content = content.replace("QPushButton {\n    background: {PALETTE['accent']};\n    color: {PALETTE['text']};", "QPushButton {\n    background: {PALETTE['accent']};\n    color: #FFFFFF;")

content = content.replace("color: {PALETTE['text']}; font-weight: bold; padding: 6px 12px", "color: #FFFFFF; font-weight: bold; padding: 6px 12px")
content = content.replace("color: {PALETTE['text']}; font-weight: bold; padding: 8px 14px", "color: #FFFFFF; font-weight: bold; padding: 8px 14px")
content = content.replace("color: {PALETTE['text']}; font-weight: bold; padding: 12px 24px", "color: #FFFFFF; font-weight: bold; padding: 12px 24px")

with open("app.py", "w") as f:
    f.write(content)
