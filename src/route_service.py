import heapq
import math

from . import map_loader


def metric_distance(coord1, coord2):
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    return math.sqrt(dlat * dlat + dlon * dlon)


def find_nearest_node(lat: float, lon: float) -> int:
    if map_loader.spatial_tree is None:
        raise RuntimeError("Graph has not been loaded yet.")

    _, nearest_index = map_loader.spatial_tree.query([lat, lon])
    return int(nearest_index)


def heuristic(node_index: int, target_lat: float, target_lon: float) -> float:
    lat_meters = 111000.0
    lon_meters = 111000.0 * math.cos(math.radians(target_lat))
    delta_lat = (map_loader.lats[node_index] - target_lat) * lat_meters
    delta_lon = (map_loader.lons[node_index] - target_lon) * lon_meters
    return math.hypot(delta_lat, delta_lon)


def a_star(start_node: int, target_node: int):
    if map_loader.G is None:
        raise RuntimeError("Graph has not been loaded yet.")

    n = map_loader.G.vcount()
    g_score = [float("inf")] * n
    came_from = [None] * n
    closed = [False] * n

    g_score[start_node] = 0.0
    open_heap = []
    tie_breaker = 0

    start_lat, start_lon = map_loader.coords_list[start_node]
    target_lat, target_lon = map_loader.coords_list[target_node]

    open_heap.append((heuristic(start_node, target_lat, target_lon), tie_breaker, start_node))
    tie_breaker += 1

    while open_heap:
        _, _, current = heapq.heappop(open_heap)

        if current == target_node:
            break

        if closed[current]:
            continue

        closed[current] = True

        for edge_id in map_loader.G.incident(current, mode="out"):
            neighbor = map_loader.G.es[edge_id].target

            if closed[neighbor]:
                continue

            tentative_cost = g_score[current] + map_loader.edge_weights[edge_id]
            if tentative_cost < g_score[neighbor]:
                g_score[neighbor] = tentative_cost
                came_from[neighbor] = current
                priority = tentative_cost + heuristic(neighbor, target_lat, target_lon)
                heapq.heappush(open_heap, (priority, tie_breaker, neighbor))
                tie_breaker += 1

    if g_score[target_node] == float("inf"):
        return {
            "status": "not_found",
            "start_coord": map_loader.coords_list[start_node],
            "target_coord": map_loader.coords_list[target_node],
            "coordinates": [],
            "distance_meters": None,
        }

    path = []
    node = target_node
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()

    return {
        "status": "ok",
        "start_coord": map_loader.coords_list[start_node],
        "target_coord": map_loader.coords_list[target_node],
        "coordinates": [map_loader.coords_list[index] for index in path],
        "distance_meters": g_score[target_node],
    }


def compute_route(start_lat: float, start_lon: float, target_lat: float, target_lon: float):
    start_node = find_nearest_node(start_lat, start_lon)
    target_node = find_nearest_node(target_lat, target_lon)

    if start_node is None or target_node is None:
        raise ValueError("Start- oder Zielknoten nicht gefunden.")

    return a_star(start_node, target_node)
