"""
ArcGIS Portal Content Dependency & Abandonment Auditor
------------------------------------------------------
This script performs a comprehensive audit of an ArcGIS Portal/Online instance.
It identifies relationships between items using four distinct strategies and
flags "Space Junk" (orphaned items) that have no incoming or outgoing links.

Outputs a JSON file compatible with the 'Feature Galaxy' D3.js visualization.
"""

from arcgis.gis import GIS
import json
import urllib3
import logging

# ------------------------------------------------------------------------------
# Configuration & Logging
# ------------------------------------------------------------------------------

# The filename for the visualization frontend
OUTPUT_FILE = "content_graph.json"

# Limits the number of items fetched to prevent timeouts on massive portals
MAX_ITEMS = 5000   

# Configure logging to both console and a logger object for audit trails
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress HTTPS warnings (common in internal enterprise environments)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ok(message):
    """Prints and logs a success message."""
    print(f"[OK] {message}")
    logger.info(message)

def err(message):
    """Prints and logs an error message."""
    print(f"[ERROR] {message}")
    logger.error(message)

# ------------------------------------------------------------------------------
# GIS Connection
# ------------------------------------------------------------------------------

def connect_to_gis():
    """
    Establishes connection to ArcGIS Online or Enterprise.
    'home' profile works automatically in Pro, Notebooks, or authenticated CLI.
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

def extract_ids_from_dict(obj, discovered=None):
    """
    Recursively scans JSON objects for 32-character ArcGIS Item IDs.
    
    Args:
        obj: The dictionary or list to scan (usually from item.get_data()).
        discovered: A set to store found IDs (handles recursion).
        
    Returns:
        A set of unique 32-character strings found within the JSON.
    """
    if discovered is None:
        discovered = set()
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            # Strategy: Look for the specific 'itemId' key used by Esri
            if key == "itemId" and isinstance(value, str) and len(value) == 32:
                discovered.add(value)
            # Strategy: Look for URLs that might contain item IDs (e.g., in popup configs)
            elif key == "url" and isinstance(value, str):
                item_id = extract_id_from_url(value)
                if item_id:
                    discovered.add(item_id)
            else:
                extract_ids_from_dict(value, discovered)
    elif isinstance(obj, list):
        for element in obj:
            extract_ids_from_dict(element, discovered)
    
    return discovered

def extract_id_from_url(url):
    """Parses a URL string to find a 32-char ArcGIS Item ID."""
    if not isinstance(url, str):
        return None
    
    # Common pattern: /home/item.html?id=... or /items/{id}
    if "/items/" in url:
        parts = url.split("/items/")
        if len(parts) > 1:
            # Strip away potential trailing paths or query strings
            item_id = parts[1].split("/")[0].split("?")[0]
            if len(item_id) == 32:
                return item_id
    
    return None

# ------------------------------------------------------------------------------
# Relationship Mining Strategies
# ------------------------------------------------------------------------------

def get_forward_relationships(item):
    """
    Strategy A1: Explicit Forward Relationships.
    Finds what this item 'points to' via the Portal API.
    """
    relationships = []
    relationship_types = ["f2w", "w2m", "m2a", "Map2Service", "Service2Data"]
    
    for rel_type in relationship_types:
        try:
            related_items = item.related_items(rel_type, direction="forward")
            for related in related_items:
                relationships.append((item.id, related.id, f"forward_{rel_type}"))
        except:
            pass
    return relationships

def get_reverse_relationships(item):
    """
    Strategy A2: Explicit Reverse Relationships.
    Finds what 'points to' this item (e.g., which App uses this Map).
    """
    relationships = []
    relationship_types = ["f2w", "w2m", "m2a", "Map2Service", "Service2Data"]
    
    for rel_type in relationship_types:
        try:
            related_items = item.related_items(rel_type, direction="reverse")
            for related in related_items:
                relationships.append((related.id, item.id, f"reverse_{rel_type}"))
        except:
            pass
    return relationships

def get_dependencies(item):
    """
    Strategy A3: Native ArcGIS Dependency API.
    Uses the built-in methods 'dependent_upon' and 'dependent_to'.
    """
    relationships = []
    # Items this item needs to function
    try:
        for dep in item.dependent_upon():
            if hasattr(dep, 'id'):
                relationships.append((item.id, dep.id, "depends_on"))
    except:
        pass
    # Items that need this item to function
    try:
        for dep in item.dependent_to():
            if hasattr(dep, 'id'):
                relationships.append((dep.id, item.id, "dependent_to"))
    except:
        pass
    return relationships

def extract_json_dependencies(item):
    """
    Strategy B: Deep JSON Inspection.
    Crawls the underlying JSON of Maps and Apps to find hidden dependencies
    that aren't formally registered in the Portal relationship database.
    """
    relationships = []
    inspect_types = [
        "Web Map", "Web Mapping Application", "Dashboard", 
        "Experience Builder", "Feature Service"
    ]
    
    try:
        if any(item_type in item.type for item_type in inspect_types):
            item_data = item.get_data()
            if item_data:
                referenced_ids = extract_ids_from_dict(item_data)
                for ref_id in referenced_ids:
                    if ref_id != item.id:
                        relationships.append((item.id, ref_id, "json_reference"))
    except:
        pass
    return relationships

# ------------------------------------------------------------------------------
# Main Audit Execution
# ------------------------------------------------------------------------------

def main():
    gis = connect_to_gis()

    ok("Fetching portal content...")
    all_items = gis.content.search(query="", max_items=MAX_ITEMS)

    nodes = {}
    edges = set()
    relationship_sources = {
        "forward_relationships": 0, "reverse_relationships": 0,
        "dependencies": 0, "json_references": 0
    }

    # STEP 1: Inventory all content
    for item in all_items:
        nodes[item.id] = {
            "id": item.id,
            "label": item.title,
            "type": item.type,
            "owner": item.owner,
            "views": item.numViews,
            "access": item.access,
            "url": item.homepage,
            "is_abandoned": True  # Assume junk until proven otherwise
        }

    ok(f"Registered {len(all_items)} items. Beginning relationship analysis...")

    # STEP 2: Cross-reference every item using all strategies
    for index, item in enumerate(all_items):
        if index % 100 == 0:
            print(f" Progress: {index}/{len(all_items)}")

        # Combine results from all strategies
        all_rels = (get_forward_relationships(item) + 
                    get_reverse_relationships(item) + 
                    get_dependencies(item) + 
                    extract_json_dependencies(item))

        for source, target, rel_type in all_rels:
            # Only track edges between items that actually exist in our inventory
            if source in nodes and target in nodes:
                edges.add((source, target))
                # Increment the specific counter for our final summary
                key = [k for k in relationship_sources if k in rel_type]
                if key: relationship_sources[key[0]] += 1
                elif "json" in rel_type: relationship_sources["json_references"] += 1
                elif "depends" in rel_type: relationship_sources["dependencies"] += 1

    # STEP 3: Identify the 'Space Junk'
    connected_ids = set()
    for source, target in edges:
        connected_ids.add(source)
        connected_ids.add(target)

    abandoned_count = 0
    for item_id in nodes:
        if item_id in connected_ids:
            nodes[item_id]["is_abandoned"] = False
        else:
            abandoned_count += 1

    # STEP 4: Save the Audit Graph
    graph = {
        "summary": {
            "total_items": len(all_items),
            "abandoned_count": abandoned_count,
            "relationship_breakdown": relationship_sources
        },
        "nodes": list(nodes.values()),
        "edges": [{"source": s, "target": t} for s, t in edges]
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    ok(f"Audit Complete. Graph saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
