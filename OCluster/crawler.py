"""
ArcGIS Portal Content Dependency Extractor
------------------------------------------

This script connects to an ArcGIS Portal or ArcGIS Online instance and builds
a dependency graph of content items such as:

- Feature Services
- Web Maps
- Dashboards
- Web Mapping Applications
- Experience Builder apps

Relationships are detected using two strategies:
1. Explicit ArcGIS item relationships
2. Deep JSON inspection to uncover implicit dependencies

The output is a graph-friendly JSON file containing:
- nodes: portal items
- edges: dependencies between items
"""

from arcgis.gis import GIS
import json
import urllib3

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

OUTPUT_FILE = "content_graph.json"
MAX_ITEMS = 5000   # Increase if your portal is very large

# Suppress HTTPS warnings for internal or self-signed portals
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------------------
# Lightweight logging helpers
# ------------------------------------------------------------------------------

def ok(message):
    print(f"[OK] {message}")

def err(message):
    print(f"[ERROR] {message}")

# ------------------------------------------------------------------------------
# GIS Connection
# ------------------------------------------------------------------------------

def connect_to_gis():
    """
    Establish a connection to the active ArcGIS environment.

    Uses GIS("home"), which works automatically in:
    - ArcGIS Pro
    - ArcGIS Notebooks
    - Logged-in Python environments

    Returns
    -------
    GIS
        Authenticated GIS object
    """
    try:
        gis = GIS("home")
        ok(f"Connected to portal: {gis.properties.portalName}")
        return gis
    except Exception as e:
        err(f"Failed to connect to GIS: {e}")
        raise

# ------------------------------------------------------------------------------
# Dependency Discovery Helpers
# ------------------------------------------------------------------------------

def extract_ids_from_dict(obj):
    """
    Recursively scan a nested dictionary or list and extract ArcGIS item IDs.

    This is used to find implicit dependencies hidden inside JSON structures,
    such as:
    - Feature Services referenced in Web Maps
    - Web Maps referenced in Apps or Dashboards

    Parameters
    ----------
    obj : dict | list
        JSON object returned by item.get_data()

    Returns
    -------
    set[str]
        Set of discovered ArcGIS item IDs
    """
    discovered = set()

    if isinstance(obj, dict):
        for key, value in obj.items():
            # ArcGIS commonly stores references using "itemId"
            if key == "itemId" and isinstance(value, str) and len(value) == 32:
                discovered.add(value)
            else:
                discovered.update(extract_ids_from_dict(value))

    elif isinstance(obj, list):
        for element in obj:
            discovered.update(extract_ids_from_dict(element))

    return discovered

# ------------------------------------------------------------------------------
# Main Processing Logic
# ------------------------------------------------------------------------------

def main():
    gis = connect_to_gis()

    print("Fetching portal content...")
    all_items = gis.content.search(query="", max_items=MAX_ITEMS)

    # Node registry (id → metadata)
    nodes = {}

    # Edge registry stored as tuples to prevent duplicates
    edges = set()

    # ------------------------------------------------------------------
    # Step 1: Register all items as nodes
    # ------------------------------------------------------------------

    for item in all_items:
        nodes[item.id] = {
            "id": item.id,
            "label": item.title,
            "type": item.type,
            "owner": item.owner,
            "views": item.numViews,
            "access": item.access
        }

    print(f"Analyzing dependencies across {len(all_items)} items...")

    # ------------------------------------------------------------------
    # Step 2: Discover relationships
    # ------------------------------------------------------------------

    for index, item in enumerate(all_items):
        if index % 100 == 0:
            print(f" Progress: {index}/{len(all_items)}")

        # --- Strategy A: Explicit ArcGIS relationships ---
        try:
            relationship_types = [
                "f2w",          # Feature → Web Map
                "w2m",          # Web Map → App
                "m2a",
                "Map2Service",
                "Service2Data"
            ]

            for rel_type in relationship_types:
                related_items = item.related_items(rel_type, direction="forward")
                for related in related_items:
                    edges.add((item.id, related.id))

        except Exception:
            # Relationship types vary across portals and items
            pass

        # --- Strategy B: Deep JSON inspection ---
        # This reveals dependencies ArcGIS does not expose as relationships
        if item.type in [
            "Web Map",
            "Web Mapping Application",
            "Dashboard",
            "Experience Builder"
        ]:
            try:
                item_data = item.get_data()
                if not item_data:
                    continue

                referenced_ids = extract_ids_from_dict(item_data)

                for ref_id in referenced_ids:
                    if ref_id in nodes and ref_id != item.id:
                        # Convention: referenced item → current item
                        edges.add((ref_id, item.id))

            except Exception:
                pass

    # ------------------------------------------------------------------
    # Step 3: Filter graph to only connected content
    # ------------------------------------------------------------------

    connected_ids = set()
    for source, target in edges:
        connected_ids.add(source)
        connected_ids.add(target)

    final_nodes = [
        nodes[item_id]
        for item_id in connected_ids
        if item_id in nodes
    ]

    final_edges = [
        {"source": source, "target": target}
        for source, target in edges
        if source in nodes and target in nodes
    ]

    # ------------------------------------------------------------------
    # Step 4: Write output
    # ------------------------------------------------------------------

    graph = {
        "nodes": final_nodes,
        "edges": final_edges
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    ok(f"Processed {len(all_items)} portal items")
    ok(f"Discovered {len(final_nodes)} connected items")
    ok(f"Captured {len(final_edges)} relationships")
    ok(f"Graph saved to {OUTPUT_FILE}")

# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
