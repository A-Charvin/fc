from arcgis.gis import GIS
from arcgis.apps.itemgraph import ItemGraph, create_dependency_graph 
import json
import urllib3
import logging
import time
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
OUTPUT_FILE = "Inventory_graph.json"
GML_FILE = "Inventory_graph.gml"
CACHE_FILE = "Inventory_cache.json"

MAX_ITEMS = 3000
SEARCH_QUERY = ""  # Leave empty for full inventory

# Performance Toggles
SAVE_GML = True                 # Set False to skip GML save/load (slower reloads)
FETCH_MISSING_SIZES = True      # Set False to skip size enrichment
SIZE_FETCH_THREADS = 20         # Parallel threads for size fetching
CACHE_MAX_AGE_HOURS = 24        # Rebuild graph if cache is older than this
# =================================================

# Suppress HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ok(message):
    print(f"[OK] {message}")
    logger.info(message)

def err(message):
    print(f"[ERROR] {message}")
    logger.error(message)

def warn(message):
    print(f"[WARN] {message}")
    logger.warning(message)

def connect_to_gis():
    try:
        gis = GIS("home")
        ok(f"Connected to portal: {gis.properties.portalName}")
        return gis
    except Exception as e:
        err(f"Failed to connect to GIS: {e}")
        raise

def extract_item_metadata(item):
    """
    Extract metadata from Item._item_info to avoid lazy loading.
    Ensures all original keys are present for visualization compatibility.
    """
    info = getattr(item, '_item_info', {}) or {}
    return {
        "id": item.id,
        "label": info.get("title") or getattr(item, 'title', ''),
        "type": info.get("type") or getattr(item, 'type', ''),
        "owner": info.get("owner") or getattr(item, 'owner', ''),
        "views": info.get("numViews", 0),
        "access": info.get("access", "private"),
        "url": info.get("url") or getattr(item, 'homepage', ''),
        "modified": info.get("modified") or getattr(item, 'modified', None),
        "created": info.get("created"),
        "size": info.get("size"),
        "tags": info.get("tags", []),
        "typeKeywords": info.get("typeKeywords", []),
        "is_abandoned": True
    }

def fetch_size_direct(gis, item_id):
    """Fetch size using direct API connection."""
    try:
        resp = gis._con.get(f"content/items/{item_id}", {"f": "json"})
        return item_id, resp.get("size") if resp else None
    except Exception:
        return item_id, None

def parallel_size_enrichment(gis, nodes):
    """Update nodes with accurate size using parallel direct API calls."""
    if not FETCH_MISSING_SIZES:
        return nodes
    
    items_to_fetch = [
        iid for iid, node in nodes.items() 
        if node.get("size") in (None, -1, 0)
    ]
    
    if not items_to_fetch:
        ok("All items have valid size; skipping enrichment")
        return nodes
    
    ok(f"Enriching size for {len(items_to_fetch)} items ({SIZE_FETCH_THREADS} threads)...")
    start = time.time()
    
    with ThreadPoolExecutor(max_workers=SIZE_FETCH_THREADS) as executor:
        future_to_id = {executor.submit(fetch_size_direct, gis, iid): iid for iid in items_to_fetch}
        for future in as_completed(future_to_id):
            item_id, size = future.result()
            if size is not None and item_id in nodes:
                nodes[item_id]["size"] = size
    
    ok(f"Size enrichment complete in {time.time() - start:.2f}s")
    return nodes

def load_cache():
    """Load previous run data if available."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        warn(f"Cache load failed: {e}")
        return None

def should_rebuild_graph(cache):
    """Determine if we need to rebuild the dependency graph."""
    if not cache:
        return True
    
    try:
        cache_time = datetime.fromisoformat(cache["summary"]["analysis_date"])
        age_hours = (datetime.now() - cache_time).total_seconds() / 3600
        if age_hours > CACHE_MAX_AGE_HOURS:
            ok(f"Cache stale ({age_hours:.1f}h)")
            return True
    except Exception:
        return True
    
    return False

def main():
    start_total = time.time()
    gis = connect_to_gis()

    # Load cache for incremental logic
    cache = load_cache()
    cache_nodes = {n["id"]: n for n in cache.get("nodes", [])} if cache else {}
    rebuild_graph = should_rebuild_graph(cache)

    # Step 1: Search Items
    ok("Fetching portal content...")
    start_search = time.time()
    
    try:
        all_items = gis.content.advanced_search(query=SEARCH_QUERY, max_items=MAX_ITEMS)
    except Exception:
        all_items = gis.content.search(query=SEARCH_QUERY, max_items=MAX_ITEMS)
    
    ok(f"Found {len(all_items)} items in {time.time() - start_search:.2f}s")

    # Step 2: Extract Metadata (No Lazy Loads)
    ok("Extracting metadata...")
    start_nodes = time.time()
    
    current_nodes = {}
    for idx, item in enumerate(all_items):
        if idx % 1000 == 0 and idx > 0:
            ok(f"  Processed {idx}/{len(all_items)}...")
        current_nodes[item.id] = extract_item_metadata(item)
    
    ok(f"Metadata extracted in {time.time() - start_nodes:.2f}s")

    # Step 3: Enrich Size (Parallel Direct API)
    current_nodes = parallel_size_enrichment(gis, current_nodes)

    # Step 4: Merge with Cache (Preserve history if unchanged)
    # We prioritize current scan data for accuracy, but keep cache if item missing
    nodes = {**cache_nodes, **current_nodes}
    
    # Remove deleted items from cache
    deleted_count = 0
    for iid in list(nodes.keys()):
        if iid not in current_nodes:
            nodes.pop(iid)
            deleted_count += 1
    if deleted_count > 0:
        ok(f"Removed {deleted_count} deleted items from cache")

    # Step 5: Build or Load Dependency Graph
    itemgraph = None
    start_graph = time.time()
    
    if rebuild_graph:
        ok("Rebuilding dependency graph...")
        try:
            itemgraph = create_dependency_graph(
                gis, all_items, outside_org=True, include_reverse=True
            )
            ok(f"Graph built in {time.time() - start_graph:.2f}s")
        except Exception as e:
            err(f"Graph build failed: {e}")
            raise
    else:
        ok("Loading graph from cache...")
        try:
            if SAVE_GML and os.path.exists(GML_FILE):
                itemgraph = ItemGraph.load_from_file(GML_FILE, gis, retrieve_items=False)
                ok(f"Graph loaded in {time.time() - start_graph:.2f}s")
            else:
                warn("GML missing; forcing rebuild")
                itemgraph = create_dependency_graph(gis, all_items, outside_org=True, include_reverse=True)
        except Exception as e:
            warn(f"Load failed ({e}); rebuilding...")
            itemgraph = create_dependency_graph(gis, all_items, outside_org=True, include_reverse=True)

    # Step 6: Process Edges and Stats
    edges = [{"source": s, "target": t, "type": "dependency"} for s, t in itemgraph.edges()]
    connected_ids = {sid for e in edges for sid in (e["source"], e["target"])}
    
    abandoned_count = 0
    for iid in nodes:
        is_connected = iid in connected_ids
        nodes[iid]["is_abandoned"] = not is_connected
        if not is_connected:
            abandoned_count += 1
    
    ok(f"Identified {abandoned_count} orphaned items")

    # Step 7: Dependency Stats
    ok("Calculating dependency stats...")
    start_stats = time.time()
    
    item_dependency_stats = {}
    for item_id in nodes.keys():
        try:
            node = itemgraph.get_node(item_id)
            if node:
                stats = {
                    "total_required_by": len(node.required_by()),
                    "total_requires": len(node.requires())
                }
                item_dependency_stats[item_id] = stats
                nodes[item_id]["dependency_info"] = {
                    "immediate_dependencies": len(node.contains()),
                    "immediate_dependents": len(node.contained_by()),
                    "total_recursive_dependencies": stats["total_requires"],
                    "total_recursive_dependents": stats["total_required_by"]
                }
        except Exception:
            continue
    
    ok(f"Stats complete in {time.time() - start_stats:.2f}s")

    # Step 8: Filter Edges for JSON
    filtered_edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    ok(f"Filtered to {len(filtered_edges)} internal relationships")

    # Step 9: High Risk Items
    critical_items = sorted(
        [
            {"id": iid, "title": nodes[iid]["label"], "type": nodes[iid]["type"], "dependents_count": s["total_required_by"]}
            for iid, s in item_dependency_stats.items() if s.get("total_required_by", 0) > 0
        ],
        key=lambda x: x["dependents_count"],
        reverse=True
    )[:50]

    # Step 10: Save Outputs
    graph_data = {
        "summary": {
            "total_items": len(nodes),
            "abandoned_count": abandoned_count,
            "connected_count": len(connected_ids),
            "total_relationships": len(filtered_edges),
            "analysis_date": datetime.now().isoformat(),
            "graph_method": "ItemGraph",
            "rebuilt_graph": rebuild_graph
        },
        "high_risk_items": critical_items,
        "nodes": list(nodes.values()),
        "edges": filtered_edges
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
    ok(f"JSON saved to {OUTPUT_FILE}")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
    ok(f"Cache saved to {CACHE_FILE}")

    if SAVE_GML and itemgraph:
        try:
            itemgraph.write_to_file(GML_FILE)
            ok(f"GML saved to {GML_FILE}")
        except Exception as e:
            warn(f"GML save failed: {e}")

    # Final Summary
    total_time = time.time() - start_total
    ok("\n" + "="*70)
    ok("AUDIT COMPLETE")
    ok("="*70)
    ok(f"Total Time: {total_time:.2f}s")
    ok(f"Items: {len(nodes)} | Orphaned: {abandoned_count} | Relations: {len(filtered_edges)}")
    ok("="*70)

if __name__ == "__main__":
    main()

# Unlike previous versions of the code, This will take a while to go through the items and give you an output,
# Let it run during end of the day or during the weekend (It might take anywhere from 20mins to 2 hours if there are too many items to go through
# The slowness is due to graph api's working.
