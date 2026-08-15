import os

import pyrosm
from scipy.spatial import cKDTree

from .config import pbf_file

G = None
nodes_gdf = None
lats = []
lons = []
osm_ids = []
osm_id_to_idx = {}
coords_list = []
edge_weights = []
spatial_tree = None


def load_graph():
    """Load the OSM network once and prepare cached lookup structures."""
    global G, nodes_gdf, lats, lons, osm_ids, osm_id_to_idx, coords_list, edge_weights, spatial_tree

    if not os.path.exists(pbf_file):
        raise FileNotFoundError(f"Datei '{pbf_file}' nicht gefunden!")

    print("Lade OSM-Daten im Hintergrund in den Arbeitsspeicher...")
    osm = pyrosm.OSM(pbf_file)

    # types: walking, driving, driving+service, cycling, all
    nodes_gdf_cycling, edges_gdf_cycling = osm.get_network(network_type="cycling", nodes=True)

    nodes_gdf, edges_gdf = nodes_gdf_cycling, edges_gdf_cycling

    G = osm.to_graph(nodes_gdf, edges_gdf, simplify=True)

    lats = G.vs["lat"]
    lons = G.vs["lon"]
    osm_ids = G.vs["id"]
    osm_id_to_idx = {node_id: idx for idx, node_id in enumerate(osm_ids)}
    coords_list = list(zip(lats, lons))
    edge_weights = G.es["length"]
    spatial_tree = cKDTree(coords_list)

    print("Kartendaten erfolgreich geladen. Einsatzbereit.")
    return G
