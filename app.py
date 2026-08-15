import os
import math
import json
import heapq
import asyncio
from pathlib import Path
import pyrosm
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from scipy.spatial import cKDTree

BASE_DIR = Path(__file__).resolve().parent

pbf_file = ""
pbf_viewport = {}
default_start = []
default_target = []


def read_city_config(config_path: str | os.PathLike | None = None):
    """Read a city config JSON file and populate the routing defaults."""
    global pbf_file, pbf_viewport, default_start, default_target

    config_file = Path(config_path) if config_path is not None else BASE_DIR / "osm_data" / "city_config.json"
    if not config_file.is_absolute():
        config_file = BASE_DIR / config_file

    if not config_file.exists():
        raise FileNotFoundError(f"Config file '{config_file}' not found.")

    with config_file.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    required_fields = ["default_start", "default_target", "pbf_viewport", "filename"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise KeyError(f"Config file '{config_file}' is missing required fields: {missing_fields}")

    pbf_viewport = config["pbf_viewport"]
    default_start = config["default_start"]
    default_target = config["default_target"]

    filename = config["filename"]
    pbf_path = Path(filename)
    if not pbf_path.is_absolute():
        pbf_path = BASE_DIR / pbf_path
    pbf_file = str(pbf_path)

    return {
        "filename": pbf_file,
        "default_start": default_start,
        "default_target": default_target,
        "pbf_viewport": pbf_viewport,
    }


read_city_config()

stream_edges = False
batch_size = 10
stream_sleep = 0.001

# --- LIFESPAN STARTUP: KARTENDATEN EINMALIG IN ARBEITSSPEICHER LADEN ---
def load_graph():
    global G, nodes_gdf
    
    if not os.path.exists(pbf_file):
        raise FileNotFoundError(f"Datei '{pbf_file}' nicht gefunden!")

    print("Lade OSM-Daten im Hintergrund in den Arbeitsspeicher...")
    osm = pyrosm.OSM(pbf_file)
    #nodes_gdf_walking, edges_gdf_walking = osm.get_network(network_type="walking", nodes=True)
    #nodes_gdf_driving, edges_gdf_driving = osm.get_network(network_type="driving", nodes=True)
    nodes_gdf_cycling, edges_gdf_cycling = osm.get_network(network_type="cycling", nodes=True)
    #nodes_gdf_driving_service, edges_gdf_driving_service = osm.get_network(network_type="driving+service", nodes=True)
    #nodes_gdf_all, edges_gdf_all = osm.get_network(network_type="all", nodes=True)

    nodes_gdf, edges_gdf = nodes_gdf_cycling, edges_gdf_cycling

    # Graph aufbauen
    G = osm.to_graph(nodes_gdf, edges_gdf, simplify=True)
    
    # Auf größten zusammenhängenden Teilgraphen reduzieren (Inseln vermeiden)
    # largest_cc = max(nx.strongly_connected_components(G_raw), key=len)
    # G = G_raw.subgraph(largest_cc).copy()

    # Nur Nodes behalten, die auch im zusammenhängenden Graphen vorkommen
    # nodes_gdf = nodes_gdf[nodes_gdf['id'].isin(G.nodes)].copy()


####

    # ==============================================================================
    # PRE-COMPUTED GRAPH MAPS & ARRAYS (Run once when graph G is created)
    # ==============================================================================
    # 1. Coordinate arrays indexed by igraph vertex index (0..N-1)
    global lats
    global lons
    global osm_ids

    lats = G.vs["lat"]  # or "lat", depending on your attribute name in G
    lons = G.vs["lon"]  # or "lon", depending on your attribute name in G
    osm_ids = G.vs["id"]

    global osm_id_to_idx
    global coords_list
    global edge_weights

    # 2. Fast mapping: OSM node ID -> igraph vertex index
    osm_id_to_idx = {node_id: idx for idx, node_id in enumerate(osm_ids)}

    # 3. Fast lookup tuple array for streaming JSON coordinates
    coords_list = list(zip(lats, lons))

    # 4. Pre-extracted edge weights array for O(1) weight lookups
    edge_weights = G.es["length"]

    global spatial_tree

    # Create spatial index ONCE when loading the graph
    # Coordinates array [lat, lon] matching igraph vertex order 0..N-1
    coords_matrix = list(zip(lats, lons))
    spatial_tree = cKDTree(coords_matrix)

####


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

def find_nearest_node(target_lat: float, target_lon: float) -> int:
    """Returns the igraph vertex index of the closest node in microsecond speed."""
    # spatial_tree returns the direct integer index (0..N-1) of the nearest neighbor
    _, nearest_vertex_idx = spatial_tree.query([target_lat, target_lon])
    return int(nearest_vertex_idx)

def get_min_edge_length_igraph(G, u_idx: int, v_idx: int) -> float:
    """
    Finds shortest edge length between two igraph vertex indices.
    Handles multigraph edges between u and v if present.
    """
    eids = G.get_eids(pairs=[(u_idx, v_idx)], directed=True, error=False)
    if eids == -1 or not eids:
        # Fallback if no direct single edge was returned
        return 1.0
    
    if isinstance(eids, int):
        return edge_weights[eids]
        
    return min(edge_weights[e] for e in eids)

# ==============================================================================
# FASTAPI SSE ENDPOINT
# ==============================================================================
@app.get("/stream-route")
async def stream_route(start_lat: float, start_lon: float, target_lat: float, target_lon: float):
    """
    Echtzeit-Streaming des A*-Fortschritts via SSE using igraph.
    """
    start_node = find_nearest_node(start_lat, start_lon)
    target_node = find_nearest_node(target_lat, target_lon)

    if start_node is None or target_node is None:
        raise HTTPException(status_code=400, detail="Start- oder Zielknoten nicht gefunden.")

    # Target node coordinates for heuristic
    target_coords = coords_list[target_node]
    target_lat_val, target_lon_val = target_coords

    # Lat/Lon scale factors in meters
    LAT_METERS = 111000.0
    LON_METERS = 111000.0 * math.cos(math.radians(target_lat_val))

    def heuristic(node_idx: int) -> float:
        """Heuristik h(n): Vectorized index access for optimal loop speed."""
        dy = (lats[node_idx] - target_lat_val) * LAT_METERS
        dx = (lons[node_idx] - target_lon_val) * LON_METERS
        return math.hypot(dx, dy)

    async def event_generator():
        try:
            start_coords = coords_list[start_node]
            
            yield {
                "event": "start_snap",
                "data": json.dumps(start_coords)
            }

            yield {
                "event": "target_snap",
                "data": json.dumps(target_coords)
            }

            num_vertices = G.vcount()
            
            # Using fixed-size arrays indexed by vertex ID for maximum performance
            g_score = [float('inf')] * num_vertices
            g_score[start_node] = 0.0
            
            previous_nodes = [None] * num_vertices
            closed_set = [False] * num_vertices

            tiecount = 0
            pq = [(heuristic(start_node), tiecount, start_node)]

            batch_edges = []
            step_counter = 0

            while pq:
                current_f, _, current_node = heapq.heappop(pq)

                if current_node == target_node:
                    break

                if closed_set[current_node]:
                    continue

                closed_set[current_node] = True
                step_counter += 1

                # Kante zum Vorgänger für die Visualisierung sammeln
                prev_node = previous_nodes[current_node]
                if prev_node is not None:
                    batch_edges.append({
                        "from": coords_list[prev_node],
                        "to": coords_list[current_node]
                    })

                if len(batch_edges) >= batch_size and stream_edges:
                    yield {
                        "event": "edges_explored",
                        "data": json.dumps({"edges": batch_edges, "step": step_counter})
                    }
                    batch_edges = []
                    await asyncio.sleep(stream_sleep)

                # Nachbarn über outgoing incident edges untersuchen
                # G.incident(current_node, mode="out") returns outgoing edge indices
                for edge_id in G.incident(current_node, mode="out"):
                    edge = G.es[edge_id]
                    neighbor = edge.target  # Target vertex index
                    
                    if closed_set[neighbor]:
                        continue

                    weight = edge_weights[edge_id]
                    tentative_g = g_score[current_node] + weight

                    if tentative_g < g_score[neighbor]:
                        g_score[neighbor] = tentative_g
                        previous_nodes[neighbor] = current_node
                        f_score = tentative_g + heuristic(neighbor)
                        tiecount += 1
                        heapq.heappush(pq, (f_score, tiecount, neighbor))

            # Restliche gepufferte Kanten senden
            if batch_edges and stream_edges:
                yield {
                    "event": "edges_explored",
                    "data": json.dumps({"edges": batch_edges, "step": step_counter})
                }

            # Route rekonstruieren
            if g_score[target_node] < float('inf'):
                path_nodes = []
                curr = target_node
                while curr is not None:
                    path_nodes.append(curr)
                    curr = previous_nodes[curr]
                path_nodes.reverse()

                route_coords = [coords_list[nid] for nid in path_nodes]

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
