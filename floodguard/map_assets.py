from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .config import MAPS_DIR, PALETTE


def ensure_placeholder_maps(cities: list[dict]) -> None:
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    for city in cities:
        path = MAPS_DIR / f"{city['name'].lower().replace(' ', '_')}.png"
        if path.exists():
            continue
        image = Image.new("RGB", (900, 620), PALETTE["background"])
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 899, 619), fill="#10243A")
        for x in range(0, 900, 75):
            draw.line((x, 0, x, 620), fill="#233247", width=1)
        for y in range(0, 620, 70):
            draw.line((0, y, 900, y), fill="#233247", width=1)
        draw.rectangle((26, 26, 874, 594), outline="#2DD4BF", width=4)
        draw.line((75, 520, 825, 92), fill="#315A7A", width=22)
        draw.line((75, 520, 825, 92), fill="#5BA7C8", width=6)
        try:
            font = ImageFont.truetype("Helvetica.ttc", 46)
            small = ImageFont.truetype("Helvetica.ttc", 20)
        except OSError:
            font = ImageFont.load_default()
            small = ImageFont.load_default()
        draw.text((46, 44), city["name"], fill=PALETTE["text"], font=font)
        draw.text((48, 102), "Calibrated placeholder map", fill=PALETTE["muted"], font=small)
        image.save(path)


 

