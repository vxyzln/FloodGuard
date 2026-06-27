from __future__ import annotations
import requests
import logging
from functools import lru_cache

class RoutingService:
    BASE_URL = "http://router.project-osrm.org"
    session = requests.Session()
    
    @staticmethod
    @lru_cache(maxsize=1024)
    def get_nearest_road(lat: float, lon: float) -> tuple[float, float] | None:
        """Snaps a given coordinate to the nearest valid road."""
        try:
            url = f"{RoutingService.BASE_URL}/nearest/v1/driving/{lon},{lat}"
            response = RoutingService.session.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "Ok" and data.get("waypoints"):
                snapped_lon, snapped_lat = data["waypoints"][0]["location"]
                return snapped_lat, snapped_lon
        except Exception as e:
            logging.error(f"Failed to snap to road: {e}")
        return None

    @staticmethod
    @lru_cache(maxsize=1024)
    def get_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> dict | None:
        """
        Calculates the shortest drivable path between two points.
        Returns a dict containing:
        - distance_km (float)
        - duration_min (float)
        - geojson (dict)
        """
        try:
            url = f"{RoutingService.BASE_URL}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
            response = RoutingService.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                return {
                    "distance_km": route["distance"] / 1000.0,
                    "duration_min": route["duration"] / 60.0,
                    "geojson": route["geometry"]
                }
        except Exception as e:
            logging.error(f"Failed to fetch route: {e}")
        return None

    @staticmethod
    def find_best_shelter(start_lat: float, start_lon: float, shelters: list[dict]) -> tuple[dict | None, dict | None]:
        """
        Finds the nearest shelter by actual road distance.
        Returns (best_shelter_dict, route_info_dict).
        """
        if not shelters:
            return None, None
            
        valid_shelters = [s for s in shelters if int(s.get("current_occupancy", 0)) < int(s.get("capacity", 0))]
        if not valid_shelters:
            return None, None
            
        coords = [f"{start_lon},{start_lat}"]
        for s in valid_shelters:
            coords.append(f"{s['longitude']},{s['latitude']}")
            
        coords_str = ";".join(coords)
        url = f"{RoutingService.BASE_URL}/table/v1/driving/{coords_str}?sources=0&annotations=distance"
        
        try:
            response = RoutingService.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "Ok" and "distances" in data:
                distances = data["distances"][0][1:]
                min_idx = -1
                min_dist = float('inf')
                for i, d in enumerate(distances):
                    if d is not None and d < min_dist:
                        min_dist = d
                        min_idx = i
                
                if min_idx >= 0:
                    best_shelter = valid_shelters[min_idx]
                    best_route = RoutingService.get_route(start_lat, start_lon, float(best_shelter["latitude"]), float(best_shelter["longitude"]))
                    return best_shelter, best_route
        except Exception as e:
            logging.error(f"Table API failed: {e}")
            
        # Fallback
        best_shelter = None
        best_route = None
        min_distance = float('inf')
        for shelter in valid_shelters:
            sh_lat, sh_lon = float(shelter["latitude"]), float(shelter["longitude"])
            route_info = RoutingService.get_route(start_lat, start_lon, sh_lat, sh_lon)
            if route_info and route_info["distance_km"] < min_distance:
                min_distance = route_info["distance_km"]
                best_shelter = shelter
                best_route = route_info
        return best_shelter, best_route

