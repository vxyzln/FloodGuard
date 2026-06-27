import re

with open("app.py", "r") as f:
    content = f.read()

# Fix QComboBox, QLineEdit, QTextEdit
content = content.replace("background: #FFFFFF;\n    border: 1px solid {PALETTE['border']};", 
                          "background: {PALETTE['surface']};\n    border: 1px solid {PALETTE['border']};")

# Fix QTableWidget
content = content.replace("QTableWidget {\n    background: #FFFFFF;",
                          "QTableWidget {\n    background: {PALETTE['surface']};")

# Fix all remaining #FFFFFF to {PALETTE['text']} (or PALETTE['text'] outside f-strings)
# Let's be careful.
content = content.replace('color: #FFFFFF;', 'color: {PALETTE[\'text\']};')
content = content.replace('color="#FFFFFF"', 'color=PALETTE["text"]')
content = content.replace('edgecolor="#FFFFFF"', 'edgecolor=PALETTE["text"]')

# In button style sheets:
content = content.replace('color: #FFFFFF;', 'color: {PALETTE[\'text\']};')

# Fix inline styles for buttons that set background to white
content = content.replace('background-color: #FFFFFF;', 'background-color: {PALETTE[\'surface\']};')

with open("app.py", "w") as f:
    f.write(content)

 