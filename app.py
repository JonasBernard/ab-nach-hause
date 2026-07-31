import os
import math
import json
import heapq
import asyncio
import pyrosm
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

pbf_file = "osm_data/kiel.osm.pbf"
pbf_viewport = {
    "left_lower": [54.231,9.882],
    "right_upper": [54.416, 10.383]
}
default_start = [54.33801, 10.14178]
default_target = [54.30776, 10.14546]

stream_sleep = 0.01

# --- LIFESPAN STARTUP: KARTENDATEN EINMALIG IN ARBEITSSPEICHER LADEN ---
def load_graph():
    global G, nodes_gdf
    
    if not os.path.exists(pbf_file):
        raise FileNotFoundError(f"Datei '{pbf_file}' nicht gefunden!")

    print("Lade OSM-Daten im Hintergrund in den Arbeitsspeicher...")
    osm = pyrosm.OSM(pbf_file)
    #nodes_gdf_walking, edges_gdf_walking = osm.get_network(network_type="walking", nodes=True)
    #nodes_gdf_driving, edges_gdf_driving = osm.get_network(network_type="driving", nodes=True)
    #nodes_gdf_cycling, edges_gdf_cycling = osm.get_network(network_type="cycling", nodes=True)
    #nodes_gdf_driving_service, edges_gdf_driving_service = osm.get_network(network_type="driving+service", nodes=True)
    nodes_gdf_all, edges_gdf_all = osm.get_network(network_type="all", nodes=True)

    nodes_gdf, edges_gdf = nodes_gdf_all, edges_gdf_all

    # Graph aufbauen
    G = osm.to_graph(nodes_gdf, edges_gdf, simplify=True)
    
    # Auf größten zusammenhängenden Teilgraphen reduzieren (Inseln vermeiden)
    # largest_cc = max(nx.strongly_connected_components(G_raw), key=len)
    # G = G_raw.subgraph(largest_cc).copy()

    # Nur Nodes behalten, die auch im zusammenhängenden Graphen vorkommen
    # nodes_gdf = nodes_gdf[nodes_gdf['id'].isin(G.nodes)].copy()
    print("Kartendaten erfolgreich geladen. Einsatzbereit.")


# Sagt der App, dass am beim Start die Kartendaten gelanden werden soll
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_graph()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/startup-coords")
def get_startup_coords():
    return {
        "defaultView": [
           (pbf_viewport["left_lower"][0] + pbf_viewport["right_upper"][0]) / 2,
           (pbf_viewport["left_lower"][1] + pbf_viewport["right_upper"][1]) / 2,
        ],
        "startPos": default_start,
        "endPos": default_target
    }

def metric_distance(coord1, coord2):
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    return math.sqrt(dlat*dlat + dlon*dlon)
 
def find_nearest_node(target_lat, target_lon):
    min_dist = float('inf')
    nearest_node_id = None
    for idx, row in nodes_gdf.iterrows():
        dist = metric_distance((target_lat, target_lon), (row['lat'], row['lon']))
        if dist < min_dist:
            min_dist = dist
            nearest_node_id = row['id']
    return nearest_node_id

def get_min_edge_length(G, u, v) -> float:
    """Ermittelt sicher die kürzeste Kantenlänge zwischen zwei Knoten."""
    edge_data = G.get_edge_data(u, v)
    if not edge_data:
        return 1.0
    
    # Falls NetworkX MultiGraph: Dict aus {edge_key: {attr_dict}}
    if isinstance(edge_data, dict):
        lengths = []
        for key, data in edge_data.items():
            if isinstance(data, dict) and 'length' in data:
                lengths.append(data['length'])
        if lengths:
            return min(lengths)
        if 'length' in edge_data:
            return edge_data['length']
            
    return 1.0

@app.get("/stream-route")
async def stream_route(start_lat: float, start_lon: float, target_lat: float, target_lon: float):
    """
    Echtzeit-Streaming des A*-Fortschritts via SSE.
    """
    start_node = find_nearest_node(start_lat, start_lon)
    target_node = find_nearest_node(target_lat, target_lon)

    if not start_node or not target_node:
        raise HTTPException(status_code=400, detail="Start- oder Zielknoten nicht gefunden.")

    # if mode == "walking":
    #    pass

    # Koordinaten des Zielknotens für die Heuristik abfragen
    target_row = nodes_gdf.loc[nodes_gdf['id'] == target_node].iloc[0]
    target_coords = (target_row['lat'], target_row['lon'])

    # TODO either use efficiently or not compute it
    coords_dict = dict(zip(nodes_gdf['id'], zip(nodes_gdf['lat'], nodes_gdf['lon'])))


    ##### Umrechnung in Meter Coordinaten
    # # Projiziert automatisch in die passende lokale UTM-Zone (in Metern)
    # nodes_gdf_projected = nodes_gdf.to_crs(nodes_gdf.estimate_utm_crs())

    # # Erstellt ein Wörterbuch: node_id -> (x_meter, y_meter)
    # node_coords_lookup = nodes_gdf_projected.set_index('id')[['x', 'y']].to_dict('index')

    # # Target-Koordinaten ebenfalls projizieren
    # target_x, target_y = target_projected_coords

    # def heuristic(node_id):
    #     coords = node_coords_lookup[node_id]
    #     dx = coords['x'] - target_x
    #     dy = coords['y'] - target_y
    #     return math.hypot(dx, dy)
    #####




    # Mittlere Breite der Region einmalig berechnen (z.B. für Deutschland ca. 51°)
    # Oder dynamisch: LAT_FACTOR = 111000, LON_FACTOR = 111000 * math.cos(math.radians(start_lat))
    LAT_METERS = 111000.0
    LON_METERS = 111000.0 * math.cos(math.radians(target_coords[0]))

    def heuristic(node_id):
        """Heuristik h(n): Luftlinie vom gegebenen Knoten zum Zielknoten in Metern."""
        node_lat, node_lon = coords_dict[node_id]
    
        dy = (float(node_lat) - target_coords[0]) * LAT_METERS
        dx = (float(node_lon) - target_coords[1]) * LON_METERS
    
        # Euklidische Distanz in Metern: sqrt(dx^2 + dy^2)
        return math.hypot(dx, dy)

        # node_x, node_y = node_coords_lookup[node_id]  # in projected meters
        # target_x, target_y = target_coords
        # return math.hypot(node_x - target_x, node_y - target_y)

        # TODO use Haversine?
        # coords = node_coords_lookup[node_id]
        # return haversine_distance((coords['lat'], coords['lon']), target_coords)

    async def event_generator():
        try:
            start_row = nodes_gdf.loc[nodes_gdf['id'] == start_node].iloc[0]
            start_coords = (start_row['lat'], start_row['lon'])
            yield {
                "event": "start_snap",
                "data": json.dumps(start_coords)
            }

            yield {
                "event": "target_snap",
                "data": json.dumps(target_coords)
            }

            tiecount = 0
            pq = [(heuristic(start_node), tiecount, start_node)]
            # Priority Queue: (f_score, a counter for ties, node_id)
            
            # g_score speichert die bisher kürzesten Distanzen vom Start
            g_score = {start_node: 0.0}
            previous_nodes = {}
            
            # Set für final evaluierte Knoten (Closed List)
            closed_set = set()

            batch_edges = []
            step_counter = 0

            while pq:
                current_f, _, current_node = heapq.heappop(pq)

                if current_node == target_node:
                    break

                if current_node in closed_set:
                    continue

                closed_set.add(current_node)
                step_counter += 1

                # Kante zum Vorgänger für die Visualisierung sammeln
                prev_node = previous_nodes.get(current_node)
                if prev_node and prev_node in coords_dict and current_node in coords_dict:
                    batch_edges.append({
                        "from": coords_dict[prev_node],
                        "to": coords_dict[current_node]
                    })

                # Stream-Batch alle 15 Schritte senden (verhindert SSE-Flaschenhals)
                if len(batch_edges) >= 15:
                    yield {
                        "event": "edges_explored",
                        "data": json.dumps({"edges": batch_edges, "step": step_counter})
                    }
                    batch_edges = []
                    assert stream_sleep != 0.0
                    await asyncio.sleep(stream_sleep)  # Gibt dem Event-Loop Zeit zum Senden

                # Nachbarn untersuchen (Open List Updates)
                for neighbor in G.neighbors(current_node):
                    if neighbor in closed_set:
                        # KORREKT: Nur abbrechen, wenn der Knoten bereits final abgeschlossen ist
                        # (Voraussetzung: Admissible/Consistent Heuristik)
                        continue

                    weight = get_min_edge_length(G, current_node, neighbor)
                    tentative_g = g_score[current_node] + weight

                    # KORREKT: Prūfen, ob dieser Weg zum Nachbarn besser ist als bisherige
                    if tentative_g < g_score.get(neighbor, float('inf')):
                        g_score[neighbor] = tentative_g
                        previous_nodes[neighbor] = current_node
                        f_score = tentative_g + heuristic(neighbor)
                        tiecount += 1
                        heapq.heappush(pq, (f_score, tiecount, neighbor))

            # Restliche gepufferte Kanten senden
            if batch_edges:
                yield {
                    "event": "edges_explored",
                    "data": json.dumps({"edges": batch_edges, "step": step_counter})
                }

            # Route rekonstruieren
            if target_node in g_score:
                path_nodes = []
                curr = target_node
                while curr is not None:
                    path_nodes.append(curr)
                    curr = previous_nodes.get(curr)
                path_nodes.reverse()

                route_coords = [coords_dict[nid] for nid in path_nodes if nid in coords_dict]

                yield {
                    "event": "route_found",
                    "data": json.dumps({
                        "distance_meters": g_score[target_node],
                        "coordinates": route_coords
                    })
                }
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Keine Route gefunden"})
                }
        except BaseException as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": "Fehler: " + str(e)})
            }


    return EventSourceResponse(event_generator())

app.mount("/", StaticFiles(directory="static", html=True), name="static")
