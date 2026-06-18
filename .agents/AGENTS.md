# FloodGuard Design and Philosophy Rules

FloodGuard is designed to feel like a professional Emergency Operations Center (EOC) used by disaster management authorities (e.g. NDMA, State Emergency Operations Centers). It should be serious, operational, and command-center grade.

## Visual Feeling
- **Do Not Use**: Futuristic sci-fi, neon cyberpunk, gaming UI, student project styling, or analytics toys.
- **Match the Theme**: Always use the dark slate/panel/teal palette (`background: #0F1B2D`, `panel: #16263D`, `border: #233247`, `accent: #2DD4BF`, `text: #E5E7EB`, `muted: #94A3B8`).

## Dashboard
- Dominant operational map, focusing on the current risk, alert level, weather, and responsive priorities.
- Do not add machine learning details or developer metrics.

## Map Layout
- Map always on the left, layer control list on the right side in a high-contrast format.
- Layers: Critical infrastructure (red triangles), population density (heatmap), river proximity (winding splines with buffer shadow), and historical flood extent (multi-level contours).

## Evacuation
- Do not expose node IDs or calculations.
- Display clear decisions: Zone, Nearest Shelter, Evacuation Priority (Critical, High, Medium, Low), Teams Required, and Boats Required.
- Allow dropdown selections of safe routes.

## AI Advisor
- Acts strictly as an Emergency Planning Assistant.
- Suggests flood risk, weather explanations, evacuation tasks, and emergency warnings. No general chat.
