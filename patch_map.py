import re

with open("app.py", "r") as f:
    content = f.read()

# We want to replace def redraw_map(self) -> None:
# and everything down to the end of the JS block.

new_func = '''    def redraw_map(self) -> None:
        if not hasattr(self, "map_view"):
            return
        city = self.current_city
        if not city:
            self.map_view.setHtml("<html><body style='background:#F8F6F2;'><h3 style='color:#111827;text-align:center;margin-top:20%;font-family:sans-serif;'>No city selected</h3></body></html>")
            return
            
        show_population = self.layer_population.isChecked()
        show_risk = self.layer_risk.isChecked()
        show_elevation = self.layer_elevation.isChecked()
        show_infra = self.layer_infra.isChecked()
        show_evac = self.layer_evac.isChecked()
        
        current_model = self.current_model
        current_zones = self.current_zones
        current_infra = self.current_infra
        current_shelters = self.current_shelters
        scenario_rainfall = self.scenario_rainfall
        scenario_river_level = self.scenario_river_level
        zone_scores = self.zone_scores
        
        self.map_view.setHtml("<html><body style='background:#F8F6F2;'><h3 style='color:#0F766E;text-align:center;margin-top:20%;font-family:sans-serif;'>Rendering High-Resolution Map Layers...</h3></body></html>")

        def map_task() -> str:
            import folium
            import numpy as np
            import math
            m = folium.Map(
                location=[city["latitude"], city["longitude"]],
                zoom_start=12,
                tiles="CartoDB positron"
            )
            
            def get_distance(lat1, lon1, lat2, lon2):
                return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5

            def get_dist_km(lat1, lon1, lat2, lon2):
                return (((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5) * 111.32

            if current_zones:
                lats = [float(z["latitude"]) for z in current_zones]
                lons = [float(z["longitude"]) for z in current_zones]
                lat_min, lat_max = min(lats) - 0.03, max(lats) + 0.03
                lon_min, lon_max = min(lons) - 0.03, max(lons) + 0.03
            else:
                lat_min, lat_max = city["latitude"] - 0.1, city["latitude"] + 0.1
                lon_min, lon_max = city["longitude"] - 0.1, city["longitude"] + 0.1

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
                    if current_infra:
                        infra_count = sum(1 for inf in current_infra if ((plat - float(inf["latitude"]))**2 + (plon - float(inf["longitude"]))**2)**0.5 <= 0.02)
                    
                    nearest_s = min(current_shelters, key=lambda s: ((plat - float(s["latitude"]))**2 + (plon - float(s["longitude"]))**2)**0.5) if current_shelters else None
                    nearest_s_name = nearest_s["name"] if nearest_s else "None"
                    
                    elev = current_model.get_elevation(plat, plon) if current_model else 15.0
                    risk = current_model.get_flood_risk(plat, plon, scenario_rainfall, scenario_river_level) if current_model else 0.0
                    
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

                for i, collection in enumerate(cs.collections):
                    color = colors[i % len(colors)]
                    for path in collection.get_paths():
                        poly = path.to_polygons()
                        if not poly:
                            continue
                        coords = [(p[1], p[0]) for p in poly[0]]
                        add_poly_to_map(coords, color, i)

                plt.close(fig)

            def get_popup_html(name, el_type, plat, plon):
                elev = current_model.get_elevation(plat, plon) if current_model else 15.0
                risk_score = current_model.get_flood_risk(plat, plon, scenario_rainfall, scenario_river_level) if current_model else 0.0
                
                if risk_score > 75.0:
                    risk_lvl = "<span style='color:red; font-weight:bold;'>CRITICAL DANGER</span>"
                    status = "<span style='color:red; font-weight:bold;'>At Risk of Inundation</span>"
                elif risk_score > 45.0:
                    risk_lvl = "<span style='color:orange; font-weight:bold;'>ELEVATED RISK</span>"
                    status = "<span style='color:orange; font-weight:bold;'>Pre-Evacuation Alert</span>"
                elif risk_score > 20.0:
                    risk_lvl = "<span style='color:#FBBF24; font-weight:bold;'>MODERATE RISK</span>"
                    status = "<span style='color:#FBBF24; font-weight:bold;'>Under Observation</span>"
                else:
                    risk_lvl = "<span style='color:green; font-weight:bold;'>LOW RISK</span>"
                    status = "<span style='color:green; font-weight:bold;'>Operational / Safe</span>"
                    
                nearest_s = min(current_shelters, key=lambda s: get_dist_km(plat, plon, s["latitude"], s["longitude"])) if current_shelters else None
                nearest_s_name = nearest_s["name"] if nearest_s else "None"
                
                river_dist = current_model.get_river_distance(plat, plon) * 111.32 if current_model else 5.0
                pop_served = int(current_model.get_population_density(plat, plon) * 12000) if current_model else 5000
                
                reco = "Continue normal operations."
                if el_type == "hospital":
                    if "At Risk" in status:
                        reco = "URGENT: Prepare ICU evacuation and backup generators."
                    else:
                        reco = "Ensure 48-hour reserve supplies are fully stocked."
                elif el_type == "power_station":
                    if "At Risk" in status:
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

            if show_population and current_model:
                grid_size = 60
                grid_lats = np.linspace(lat_min, lat_max, grid_size)
                grid_lons = np.linspace(lon_min, lon_max, grid_size)
                
                grid_vals = np.zeros((grid_size, grid_size))
                for i, lt in enumerate(grid_lats):
                    for j, ln in enumerate(grid_lons):
                        grid_vals[i, j] = current_model.get_population_density(lt, ln) * 100.0
                        
                pop_colors = ["#E5E7EB", "#93C5FD", "#14B8A6", "#FBBF24", "#F97316", "#EF4444"]
                pop_levels = [-1.0, 15.0, 35.0, 55.0, 75.0, 90.0, 101.0]
                add_contour_layer(grid_vals, pop_colors, pop_levels, layer_name="population")
                
            if show_risk and current_zones and current_model:
                risk_vals = [zone_scores.get(int(z["zone_id"]), 0.0) / 100.0 for z in current_zones]
                
                grid_size = 40
                grid_lats = np.linspace(lat_min, lat_max, grid_size)
                grid_lons = np.linspace(lon_min, lon_max, grid_size)
                grid_vals = np.zeros((grid_size, grid_size))
                for i, lt in enumerate(grid_lats):
                    for j, ln in enumerate(grid_lons):
                        risk_score = current_model.get_flood_risk(lt, ln, scenario_rainfall, scenario_river_level)
                        hist_freq = current_model.get_historical_flood_frequency(lt, ln)
                        grid_vals[i, j] = risk_score * 0.85 + hist_freq * 15.0
                        
                risk_colors = ["#10B981", "#FBBF24", "#F97316", "#EF4444", "#7F1D1D"]
                risk_levels = [-1.0, 30.0, 50.0, 70.0, 85.0, 101.0]
                add_contour_layer(grid_vals, risk_colors, risk_levels)
                
            if show_elevation and current_model:
                grid_size = 40
                grid_lats = np.linspace(lat_min, lat_max, grid_size)
                grid_lons = np.linspace(lon_min, lon_max, grid_size)
                
                grid_vals = np.zeros((grid_size, grid_size))
                for i, lt in enumerate(grid_lats):
                    for j, ln in enumerate(grid_lons):
                        grid_vals[i, j] = current_model.get_elevation(lt, ln)
                        
                min_e = np.min(grid_vals)
                max_e = np.max(grid_vals)
                span = max_e - min_e if max_e > min_e else 1.0
                normalized = (grid_vals - min_e) / span * 100.0
                
                elev_colors = ["#7F1D1D", "#F97316", "#FBBF24", "#86EFAC", "#064E3B"]
                elev_levels = [-1.0, 20.0, 40.0, 60.0, 80.0, 101.0]
                add_contour_layer(normalized, elev_colors, elev_levels)
                
            if show_infra and current_infra:
                for inf in current_infra:
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
                    
            if show_evac and current_shelters:
                for idx, s in enumerate(current_shelters):
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
                    
            legend_html = \'''
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
            \'''
            m.get_root().html.add_child(folium.Element(legend_html))
                
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
            return html

        def on_map_success(html: str) -> None:
            self.map_view.setHtml(html)

        self.run_background(map_task, on_map_success)
'''

import re
start_idx = content.find("    def redraw_map(self) -> None:")
end_idx = content.find("    def refresh_evacuation(self) -> None:")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_func + "\n" + content[end_idx:]
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched redraw_map!")
else:
    print("Could not find start/end bounds for redraw_map.")
