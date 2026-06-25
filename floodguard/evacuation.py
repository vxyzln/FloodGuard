from __future__ import annotations

import math

import networkx as nx


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class EvacuationPlanner:
    def __init__(self, zones: list[dict], shelters: list[dict]) -> None:
        self.zones = zones
        self.shelters = shelters
        self.blocked_edges: set[tuple[str, str]] = set()

    def build_graph(self) -> nx.Graph:
        graph = nx.Graph()
        for zone in self.zones:
            graph.add_node(f"zone:{zone['zone_id']}", kind="zone", payload=zone, latitude=zone["latitude"], longitude=zone["longitude"])
        for shelter in self.shelters:
            graph.add_node(
                f"shelter:{shelter['shelter_id']}",
                kind="shelter",
                payload=shelter,
                latitude=shelter["latitude"],
                longitude=shelter["longitude"],
            )
        nodes = list(graph.nodes(data=True))
        for i, (node_a, data_a) in enumerate(nodes):
            distances = []
            for node_b, data_b in nodes:
                if node_a == node_b:
                    continue
                dist = haversine_km(data_a["latitude"], data_a["longitude"], data_b["latitude"], data_b["longitude"])
                distances.append((dist, node_b))
            for dist, node_b in sorted(distances)[:4]:
                edge = tuple(sorted((node_a, node_b)))
                if edge not in self.blocked_edges:
                    graph.add_edge(node_a, node_b, weight=dist)
        return graph

    def block_edge(self, edge_label: str) -> None:
        if " -> " not in edge_label:
            return
        left, right = edge_label.split(" -> ", 1)
        self.blocked_edges.add(tuple(sorted((left, right))))

    def available_edge_labels(self) -> list[str]:
        graph = self.build_graph()
        return [f"{a} -> {b}" for a, b in graph.edges]

    def plan(self, zone_risks: dict[int, float]) -> list[dict]:
        graph = self.build_graph()
        rows = []
        available_shelters = [
            shelter for shelter in self.shelters if int(shelter["current_occupancy"]) < int(shelter["capacity"])
        ] or self.shelters
        for zone in self.zones:
            source = f"zone:{zone['zone_id']}"
            candidates = []
            for shelter in available_shelters:
                target = f"shelter:{shelter['shelter_id']}"
                try:
                    distance = float(nx.shortest_path_length(graph, source, target, weight="weight"))
                    path = nx.shortest_path(graph, source, target, weight="weight")
                    candidates.append((distance, shelter, path))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
            if not candidates:
                continue
            distance, shelter, path = min(candidates, key=lambda item: item[0])
            risk = float(zone_risks.get(zone["zone_id"], 0))
            priority = risk * int(zone["population"]) / max(distance, 0.25)
            rows.append(
                {
                    "zone": zone,
                    "shelter": shelter,
                    "distance_km": distance,
                    "path": path,
                    "risk": risk,
                    "priority_score": priority,
                    "teams": max(1, math.ceil(priority / 75000)),
                    "boats": max(0, math.ceil((risk - 55) / 18)) if risk > 55 else 0,
                }
            )
        return sorted(rows, key=lambda row: row["priority_score"], reverse=True)


