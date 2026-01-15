from arcgis.gis import GIS
from arcgis.apps.itemgraph import ItemGraph, create_dependency_graph 
import json
import urllib3
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
OUTPUT_FILE = "content_audit_graph.json"
GML_FILE = "content_audit_graph.gml"
MAX_ITEMS = 5000   

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

def main():
    gis = connect_to_gis()

    ok("Fetching portal content...")
    all_items = gis.content.search(query="", max_items=MAX_ITEMS)
    ok(f"Found {len(all_items)} items in portal")

    # Node registry (id → metadata)
    nodes = {}
    
    # Step 1: Register ALL items as nodes
    for item in all_items:
        nodes[item.id] = {
            "id": item.id,
            "label": item.title,
            "type": item.type,
            "owner": item.owner,
            "views": item.numViews,
            "access": item.access,
            "url": item.homepage,
            "modified": item.modified,
            "is_abandoned": True
        }

    ok(f"Registered {len(all_items)} items as nodes")

    # Step 2: Create comprehensive dependency graph using ItemGraph
    print("\nBuilding comprehensive dependency graph...")
    print("(This recursively explores ALL dependencies - may take several minutes for large portals)\n")
    
    try:
        itemgraph = create_dependency_graph(
            gis,
            all_items,
            outside_org=True,
            include_reverse=True
        )
        
        ok(f"ItemGraph built with {len(itemgraph.all_items())} total nodes")
        
    except Exception as e:
        err(f"Failed to create dependency graph: {e}")
        raise

    # Step 3: Extract edges from ItemGraph
    edges = []
    
    for source_id, target_id in itemgraph.edges():
        edges.append({
            "source": source_id,
            "target": target_id,
            "type": "dependency"
        })
    
    ok(f"Extracted {len(edges)} relationships from ItemGraph")

    # Step 4: Identify connected items
    connected_ids = set()
    for edge in edges:
        connected_ids.add(edge["source"])
        connected_ids.add(edge["target"])

    abandoned_count = 0
    for item_id in nodes.keys():
        if item_id in connected_ids:
            nodes[item_id]["is_abandoned"] = False
        else:
            abandoned_count += 1

    ok(f"Space junk identified: {abandoned_count} items with no relationships")

    # Step 5: Analyze each item's dependency structure
    print("\nAnalyzing item dependency structure...")
    
    item_dependency_stats = {}
    
    for item_id in nodes.keys():
        try:
            node = itemgraph.get_node(item_id)
            if node:
                contains = node.contains()
                contained_by = node.contained_by()
                
                item_dependency_stats[item_id] = {
                    "contains_count": len(contains),
                    "contained_by_count": len(contained_by),
                    "total_requires": len(node.requires()),
                    "total_required_by": len(node.required_by())
                }
                
                nodes[item_id]["dependency_info"] = {
                    "immediate_dependencies": len(contains),
                    "immediate_dependents": len(contained_by),
                    "total_recursive_dependencies": len(node.requires()),
                    "total_recursive_dependents": len(node.required_by())
                }
        except Exception as e:
            pass

    ok("Item dependency analysis complete")

    # Step 6: Filter edges strictly for Web Visualization
    # We only want to draw lines between items that actually exist in our 'nodes' list
    # This prevents D3.js errors when external items are referenced
    filtered_edges = []
    skipped_external_refs = 0
    
    for edge in edges:
        s = edge["source"]
        t = edge["target"]
        
        # Check if BOTH ends of the relationship are in our scanned items
        if s in nodes and t in nodes:
            filtered_edges.append(edge)
        else:
            skipped_external_refs += 1
    
    ok(f"Filtered to {len(filtered_edges)} valid internal relationships for JSON")
    if skipped_external_refs > 0:
        ok(f"Skipped {skipped_external_refs} external references (preserved in GML)")

    # Step 7: Identify high-risk items
    critical_items = []
    for item_id, stats in item_dependency_stats.items():
        if stats["total_required_by"] > 0:
            critical_items.append({
                "id": item_id,
                "title": nodes[item_id]["label"],
                "type": nodes[item_id]["type"],
                "dependents_count": stats["total_required_by"]
            })
    
    critical_items.sort(key=lambda x: x["dependents_count"], reverse=True)
    critical_items = critical_items[:50]

    # Step 8: Prepare final output
    final_nodes = list(nodes.values())

    graph_data = {
        "summary": {
            "total_items": len(all_items),
            "abandoned_count": abandoned_count,
            "connected_count": len(connected_ids),
            "total_relationships": len(filtered_edges),
            "analysis_date": datetime.now().isoformat(),
            "graph_method": "ItemGraph (arcgis.apps.itemgraph.create_dependency_graph)"
        },
        "high_risk_items": critical_items,
        "nodes": final_nodes,
        "edges": filtered_edges
    }

    # Save JSON output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
    ok(f"JSON output saved to {OUTPUT_FILE}")

    # Save GML format for visualization and future reload
    try:
        itemgraph.write_to_file(GML_FILE)
        ok(f"GML structure saved to {GML_FILE}")
    except Exception as e:
        warn(f"Could not save GML file: {e}")

    # Print final summary
    ok("="*70)
    ok("AUDIT COMPLETE - COMPREHENSIVE DEPENDENCY ANALYSIS")
    ok("="*70)
    ok(f"Total items scanned: {graph_data['summary']['total_items']}")
    ok(f"Items with relationships: {graph_data['summary']['connected_count']}")
    ok(f"Orphaned/Abandoned items: {graph_data['summary']['abandoned_count']}")
    ok(f"Total relationships found: {graph_data['summary']['total_relationships']}")
    
    ok(f"\nTop 10 most critical items (most dependents):")
    for i, item in enumerate(critical_items[:10], 1):
        ok(f"  {i}. {item['title'][:50]} ({item['type']}) - {item['dependents_count']} dependents")
    
    ok(f"\nOutputs saved:")
    ok(f"  - JSON: {OUTPUT_FILE}")
    ok(f"  - GML:  {GML_FILE}")
    ok("="*70)

if __name__ == "__main__":
    main()

# Unlike previous versions of the code, This will take a while to go through the items and give you an output,
# Let it run during end of the day or during the weekend (It might take anywhere from 20mins to 2 hours if there are too many items to go through
# Tried to see if I could make it show the progress as it is going through, but that's not here yet, May be you can get it to show.
# This will give a very comprehensive version using the existing tool.
