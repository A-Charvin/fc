"""
ArcGIS Organization Dependency Crawler (WIP v6)
=============================================================
- Will iterate and add in a few more things (Groups, Users etc)
"""

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import re
import json
import time
import os
import glob
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import networkx as nx
import requests
from requests.adapters import HTTPAdapter
from collections import defaultdict

from arcgis.gis import GIS

# ================= CONFIGURATION =================
FILE_BASE_NAME = "Inventory_graph"
STATE_BASE_NAME = "inventory_state"
SCHEMA_VERSION = 6

MAX_WORKERS = 12
SIZE_WORKERS = 20
SIZE_CHUNK = 100
KEEP_OLD_STATES = 5
KEEP_OLD_JSON = 3
KEEP_OLD_LOGS = 10
JSON_INDENT = None

# Regex patterns
ID_RE = re.compile(r'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])', re.I)
SVC_RE = re.compile(r'https?://[^\s"\'?#]+?/(?:Feature|Map|Image|VectorTile|Scene)Server', re.I)
ERROR_STATUS_RE = re.compile(r'\b(400|403|404)\b')
ERROR_TEXT_RE = re.compile(r'\b(not found|does not exist|invalid url|item does not exist)\b', re.I)
NONE_TYPE_ERROR = "the JSON object must be str, bytes or bytearray, not NoneType"

# Type routing based on measured yield data
# Types where /data parsing finds edges
TYPES_WITH_DATA = {
    "Web Map", "Web Scene", "Dashboard", "Web Experience",
    "Web Mapping Application", "StoryMap", "Hub Site Application", "Hub Page"
}

# Types where /relatedItems (no-param) finds edges
TYPES_WITH_RELATED = {
    "Feature Service", "Map Service", "Form", "Map Area",
    "Web Map", "Web Mapping Application", "Dashboard", "StoryMap",
    "Solution", "Notebook", "Mission", "Mobile Application",
    "Style", "Scene Service", "Vector Tile Service",
    "WFS", "WMS", "WMTS", "StoryMap Theme", "QuickCapture Project",
    "Geoprocessing Service", "Feature Collection", "Hub Page",
    "Hub Site Application", "Web Experience", "Web Scene"
}

# Types where BOTH /data and /relatedItems find edges
TYPES_WITH_BOTH = {
    "Web Map", "Web Mapping Application"
}

# Types to skip entirely (0 edges from both sources in this org)
TYPES_TO_SKIP = {
    "Notebook", "WMS"
}

STATIC_ITEM_TYPES = {
    "PDF", "Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint",
    "CSV", "Image", "Shapefile", "Code Attachment", "Report",
    "Scene Package", "Layer Package", "GeoJson", "KML", "CAD Drawing",
    "Tile Package", "Vector Tile Package", "File Geodatabase",
    "Service Definition", "Project Package", "Map Package",
    "Mobile Map Package", "Compact Tile Package", "Explorer Map",
    "Explorer Layer", "Document Link", "GeoProcessing Sample",
    "Operation View", "Workflow Manager Diagram", "Big Data File Share",
    "Raster Function Template", "Visio Document", "Route Layer"
}

TYPES_WITH_SIZE = {
    "File Geodatabase", "Shapefile", "CSV", "Image", "PDF",
    "Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint",
    "KML", "GeoJson", "Scene Package", "Layer Package",
    "Tile Package", "Vector Tile Package", "Map Package",
    "Mobile Map Package", "Compact Tile Package", "Service Definition",
    "Project Package", "CAD Drawing", "Visio Document"
}
# =================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_TIMESTAMP = time.strftime("%Y%m%d_%H%M%S")

OUTPUT_FILE = os.path.join(SCRIPT_DIR, f"{FILE_BASE_NAME}_{RUN_TIMESTAMP}.json")
STATE_FILE = os.path.join(SCRIPT_DIR, f"{STATE_BASE_NAME}_{RUN_TIMESTAMP}.json")
LOG_FILE = os.path.join(SCRIPT_DIR, f"inventory_run_{RUN_TIMESTAMP}.log")

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8')]
)
logger = logging.getLogger(__name__)

def ok(msg):
    print(f"[OK] {msg}")
    logger.info(msg)

def warn(msg):
    print(f"[WARN] {msg}")
    logger.warning(msg)

def err(msg):
    print(f"[ERROR] {msg}")
    logger.error(msg)

# ================= UTILITIES =================
def normalize_url(url):
    """Normalize URL: lowercase, https, strip layer IDs and trailing slashes."""
    if not url:
        return ""
    url = url.lower().strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    # Strip everything after the Server endpoint (layer IDs, query params)
    for server_type in ['featureserver', 'mapserver', 'imageserver', 'vectortileserver', 'sceneserver']:
        idx = url.find(server_type)
        if idx != -1:
            url = url[:idx + len(server_type)]
            break
    return url.rstrip('/')

def format_size(size_mb):
    if size_mb is None:
        return "Unknown"
    if size_mb < 1:
        return f"{size_mb * 1024:.1f} KB"
    elif size_mb < 1024:
        return f"{size_mb:.1f} MB"
    else:
        return f"{size_mb / 1024:.2f} GB"

# ================= ATOMIC FILE WRITES =================
def atomic_write_json(filepath, data):
    dir_name = os.path.dirname(filepath)
    fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=JSON_INDENT)
        shutil.move(temp_path, filepath)
    except Exception:
        try:
            os.remove(temp_path)
        except Exception:
            pass
        raise

# ================= STATE MANAGEMENT =================
def find_latest_file(pattern):
    search_pattern = os.path.join(SCRIPT_DIR, pattern)
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def load_state():
    files = sorted(glob.glob(os.path.join(SCRIPT_DIR, f"{STATE_BASE_NAME}_*.json")),
                   key=os.path.getctime, reverse=True)
    for f in files[:3]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("_schema_version") != SCHEMA_VERSION:
                warn(f"State schema version mismatch ({data.get('_schema_version')} != {SCHEMA_VERSION}). "
                     f"Forcing full rescan.")
                return {}
            if f != files[0]:
                ok(f"Loaded fallback state: {os.path.basename(f)}")
            else:
                ok(f"Loaded state: {os.path.basename(f)}")
            return data
        except Exception as e:
            warn(f"State file {os.path.basename(f)} corrupt: {e}")
    return {}

def save_state(state):
    state["_schema_version"] = SCHEMA_VERSION
    atomic_write_json(STATE_FILE, state)
    ok(f"State saved: {os.path.basename(STATE_FILE)}")
    cleanup_old_files(f"{STATE_BASE_NAME}_*.json", KEEP_OLD_STATES)

def cleanup_old_files(pattern, keep_count):
    files = sorted(glob.glob(os.path.join(SCRIPT_DIR, pattern)),
                   key=os.path.getctime, reverse=True)
    for old_file in files[keep_count:]:
        try:
            os.remove(old_file)
        except Exception:
            pass

# ================= INVENTORY & URL MAP =================
def inventory_org_items(gis, query="*"):
    ok("Fetching organization inventory...")
    org_id = gis.properties.id
    org_filter = f'orgid:"{org_id}"'

    first_page = gis.content.advanced_search(
        query=org_filter, max_items=100,
        sort_field="created", sort_order="asc", as_dict=True
    )
    total = int(first_page.get("total", 0))
    first_results = first_page.get("results", [])

    if total == 0 or not first_results:
        ok("Found 0 items.")
        return {}, {}

    min_ms = next((r.get("created") for r in first_results
                   if isinstance(r.get("created"), int) and r["created"] > 0), 0)

    if total <= 100:
        max_ms = next((r.get("created") for r in first_results
                       if isinstance(r.get("created"), int) and r["created"] > 0), 0)
    else:
        last_page = gis.content.advanced_search(
            query=org_filter, max_items=1,
            sort_field="created", sort_order="desc", as_dict=True
        )
        max_ms = next((r.get("created") for r in last_page.get("results", [])
                       if isinstance(r.get("created"), int) and r["created"] > 0),
                      int(time.time() * 1000))

    all_items = list(first_results)
    seen_ids = {d["id"] for d in first_results if d.get("id")}
    url_map = {}
    for r in first_results:
        if r.get("url"):
            url_map[normalize_url(r["url"])] = r["id"]

    ranges = [(min_ms, max_ms)]
    MIN_RANGE_MS = 3600_000

    while ranges:
        ms0, ms1 = ranges.pop()
        q = f"({org_filter}) AND ({query}) AND created:[{ms0} TO {ms1}]"
        count_resp = gis.content.advanced_search(query=q, max_items=1, as_dict=True)
        range_total = int(count_resp.get("total", 0))

        if range_total >= 10000:
            if (ms1 - ms0) <= MIN_RANGE_MS:
                warn(f"Date range floor reached ({ms0}-{ms1}) with {range_total} items. "
                     f"Fetching first 10,000 only.")
            else:
                mid = (ms0 + ms1) // 2
                ranges.append((mid + 1, ms1))
                ranges.append((ms0, mid))
                continue

        start = 1
        while True:
            page = gis.content.advanced_search(
                query=q, start=start, max_items=100, as_dict=True
            )
            results = page.get("results", [])
            if not results:
                break
            for r in results:
                rid = r.get("id")
                if rid and rid not in seen_ids:
                    all_items.append(r)
                    seen_ids.add(rid)
                    if r.get("url"):
                        url_map[normalize_url(r["url"])] = rid
            start = page.get("nextStart", -1)
            if start == -1:
                break

    ok(f"Found {len(all_items):,} items. Built URL map with {len(url_map)} entries.")
    return {d["id"]: d for d in all_items if d.get("id")}, url_map

# ================= SMART RETRY FETCHER =================
def fetch_with_retry(gis, url, params, max_retries=3, allow_none_for_types=None):
    """Returns: (data, status, elapsed_time)
    status: 'ok' | 'expected_error' | 'failure'
    """
    start_time = time.time()
    for attempt in range(max_retries):
        try:
            resp = gis._con.get(url, params)
            # Check for HTTP 200 with error body
            if isinstance(resp, dict) and "error" in resp:
                error_code = resp.get("error", {}).get("code", 0)
                if error_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                elif error_code in (400, 403, 404):
                    return None, "expected_error", time.time() - start_time
                else:
                    return None, "failure", time.time() - start_time
            return resp, "ok", time.time() - start_time
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                retry_val = e.response.headers.get('Retry-After', '2')
                try: delay = int(retry_val)
                except ValueError: delay = 2
                time.sleep(delay)
                continue
            elif status >= 500:
                time.sleep(2 ** attempt)
                continue
            else:
                return None, "expected_error", time.time() - start_time
        except Exception as e:
            err_str = str(e)
            
            # FIX: Treat NoneType JSON errors as expected for StoryMap/WMA
            if NONE_TYPE_ERROR in err_str and allow_none_for_types:
                return None, "expected_error", time.time() - start_time
            
            status_match = ERROR_STATUS_RE.search(err_str)
            text_match = ERROR_TEXT_RE.search(err_str)
            
            if status_match or text_match:
                return None, "expected_error", time.time() - start_time
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None, "failure", time.time() - start_time
    return None, "failure", time.time() - start_time

# ================= SIZE ENRICHMENT =================
def fetch_item_size_hydrated(item_id, gis):
    try:
        item = gis.content.get(item_id)
        if item is None:
            return item_id, None, None, False
        size_bytes = getattr(item, "size", None)
        attachments_bytes = getattr(item, "attachments_size", None)
        
        if size_bytes is not None and size_bytes >= 0:
            size_mb = round(size_bytes / (1024 * 1024), 2)
            if size_mb == -0.0: size_mb = 0.0
        else:
            size_mb = None
            
        if attachments_bytes is not None and attachments_bytes >= 0:
            attachments_mb = round(attachments_bytes / (1024 * 1024), 2)
            if attachments_mb == -0.0: attachments_mb = 0.0
        else:
            attachments_mb = None
            
        return item_id, size_mb, attachments_mb, True
    except Exception:
        return item_id, None, None, False

def enrich_sizes(gis, items_needing_size):
    if not items_needing_size:
        return {}
    
    ok(f"Enriching file sizes for {len(items_needing_size)} items (hydrated)...")
    sizes = {}
    failed = 0
    total = len(items_needing_size)
    t0 = time.perf_counter()
    last_print_t = t0
    
    for start in range(0, total, SIZE_CHUNK):
        end = min(start + SIZE_CHUNK, total)
        chunk_ids = items_needing_size[start:end]
        
        with ThreadPoolExecutor(max_workers=SIZE_WORKERS) as executor:
            results = list(executor.map(
                lambda iid: fetch_item_size_hydrated(iid, gis), chunk_ids
            ))
        
        for item_id, size_mb, attachments_mb, success in results:
            sizes[item_id] = {"size_mb": size_mb, "attachments_size_mb": attachments_mb}
            if not success:
                failed += 1
        
        processed = start + len(chunk_ids)
        total_elapsed = time.perf_counter() - t0
        chunk_elapsed = time.perf_counter() - last_print_t
        ok(f"  Size progress: {processed}/{total} ({processed/total:.1%}) "
           f"in {total_elapsed:.1f}s [chunk took {chunk_elapsed:.1f}s]")
        last_print_t = time.perf_counter()
    
    if failed > 0:
        warn(f"  {failed} items failed size hydration")
    return sizes

# ================= DEPENDENCY EXTRACTOR =================
def extract_ids_from_dict(obj, self_id_lower, org_ids, url_map):
    found = set()
    
    def walk(value):
        if isinstance(value, str):
            if len(value) < 32:
                return
            for m in ID_RE.findall(value):
                m_lower = m.lower()
                if m_lower in org_ids and m_lower != self_id_lower:
                    found.add(m_lower)
            if 'server' in value.lower():
                for u in SVC_RE.findall(value):
                    normalized_url = normalize_url(u)
                    target_id = url_map.get(normalized_url)
                    if target_id and target_id != self_id_lower:
                        found.add(target_id)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
                
    walk(obj)
    return found

def extract_dependencies(item_id, item_type, all_org_ids, url_map, gis):
    """Optimized extraction based on measured yield data."""
    item_id_lower = item_id.lower()
    edges = set()
    metrics = {
        "data_calls": 0, "data_time": 0.0, "data_failures": 0, "data_expected_errors": 0,
        "related_calls": 0, "related_time": 0.0, "related_failures": 0, "related_expected_errors": 0,
        "resource_calls": 0, "resource_time": 0.0, "resource_failures": 0, "resource_expected_errors": 0,
        "non_dict_responses": 0
    }
    success = True

    # Skip static items and types with zero yield
    if item_type in STATIC_ITEM_TYPES or item_type in TYPES_TO_SKIP:
        return item_id, list(edges), success, metrics

    # 1. /data JSON parsing (only for types where it finds edges)
    if item_type in TYPES_WITH_DATA:
        metrics["data_calls"] += 1
        # Allow NoneType errors for StoryMap/WMA (they legitimately have no /data)
        allow_none = item_type in ("StoryMap", "Web Mapping Application")
        data, status, elapsed = fetch_with_retry(
            gis, f"content/items/{item_id}/data", {"f": "json"},
            allow_none_for_types=allow_none
        )
        metrics["data_time"] += elapsed
        if status == "failure":
            metrics["data_failures"] += 1
            success = False
        elif status == "expected_error":
            metrics["data_expected_errors"] += 1
        elif data is not None and isinstance(data, (dict, list)):
            edges.update((item_id_lower, tid) for tid in extract_ids_from_dict(data, item_id_lower, all_org_ids, url_map))
        elif data is not None:
            metrics["non_dict_responses"] += 1

    # 2. /relatedItems - NO PARAM (finds more edges than typed calls)
    if item_type in TYPES_WITH_RELATED:
        metrics["related_calls"] += 1
        data, status, elapsed = fetch_with_retry(
            gis, f"content/items/{item_id}/relatedItems",
            {"direction": "forward", "f": "json"}
        )
        metrics["related_time"] += elapsed
        if status == "failure":
            metrics["related_failures"] += 1
            success = False
        elif status == "expected_error":
            metrics["related_expected_errors"] += 1
        elif data and isinstance(data, dict):
            for rel in data.get("relatedItems", []):
                target_id = rel.get("id", "").lower()
                if target_id and target_id in all_org_ids and target_id != item_id_lower:
                    edges.add((item_id_lower, target_id))
        elif data is not None:
            metrics["non_dict_responses"] += 1

    # 3. Targeted Resource Fetching (for types with draft/config files)
    resource_endpoints = []
    if item_type == "Web Experience":
        resource_endpoints.append(f"content/items/{item_id}/resources/config/config.json")
    elif item_type == "QuickCapture Project":
        resource_endpoints.append(f"content/items/{item_id}/resources/qc.project.json")
    elif item_type == "Geoprocessing Service":
        resource_endpoints.append(f"content/items/{item_id}/resources/webtoolDefinition.json")
    elif item_type in ["StoryMap", "Hub Site Application", "Hub Page"]:
        metrics["resource_calls"] += 1
        res_list, status, elapsed = fetch_with_retry(gis, f"content/items/{item_id}/resources", {"f": "json"})
        metrics["resource_time"] += elapsed
        if status == "failure":
            metrics["resource_failures"] += 1
            success = False
        elif status == "expected_error":
            metrics["resource_expected_errors"] += 1
        elif res_list and isinstance(res_list, dict):
            for res in res_list.get("resources", []):
                res_name = res.get("resource", "")
                if "draft" in res_name and "express" not in res_name and res_name.endswith(".json"):
                    resource_endpoints.append(f"content/items/{item_id}/resources/{res_name}")
        elif res_list is not None:
            metrics["non_dict_responses"] += 1

    for endpoint in resource_endpoints:
        metrics["resource_calls"] += 1
        data, status, elapsed = fetch_with_retry(gis, endpoint, {"f": "json"})
        metrics["resource_time"] += elapsed
        if status == "failure":
            metrics["resource_failures"] += 1
            success = False
        elif status == "expected_error":
            metrics["resource_expected_errors"] += 1
        elif data is not None and isinstance(data, (dict, list)):
            edges.update((item_id_lower, tid) for tid in extract_ids_from_dict(data, item_id_lower, all_org_ids, url_map))
        elif data is not None:
            metrics["non_dict_responses"] += 1

    return item_id, list(edges), success, metrics

# ================= MAIN EXECUTION =================
def main():
    start_total = time.time()
    ok(f"Starting run. Timestamp: {RUN_TIMESTAMP}")
    ok(f"Schema version: {SCHEMA_VERSION}")

    try:
        gis = GIS("home")
        ok(f"Connected to: {gis.properties.name} (Org ID: {gis.properties.id})")

        pool_size = max(MAX_WORKERS, SIZE_WORKERS) + 2
        try:
            adapter = HTTPAdapter(
                pool_connections=pool_size,
                pool_maxsize=pool_size,
                max_retries=0
            )
            gis._con._session.mount('https://', adapter)
            gis._con._session.mount('http://', adapter)
        except (AttributeError, KeyError) as e:
            warn(f"Could not resize connection pool: {e}. Proceeding with defaults.")
    except Exception as e:
        err(f"Connection failed: {e}")
        return

    # 1. Load previous state AND edges
    previous_state = load_state()
    ok(f"Loaded state: {len(previous_state)} items tracked.")

    prev_edges = []
    prev_json = find_latest_file(f"{FILE_BASE_NAME}_*.json")
    if prev_json:
        try:
            with open(prev_json, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            prev_edges = prev_data.get("edges", [])
            ok(f"Loaded previous graph: {len(prev_edges)} edges.")
        except Exception as e:
            warn(f"Could not load previous JSON: {e}")

    # 2. Fetch live inventory + URL map
    live_items_dict, url_map = inventory_org_items(gis, query="*")
    if not live_items_dict:
        warn("No items found. Exiting.")
        return

    # 3. Classify delta
    new_ids, changed_ids, unchanged_ids, retry_ids = [], [], [], []
    live_ids = set(live_items_dict.keys())
    previously_failed = set(previous_state.get("_failed_ids", []))

    for item_id, d in live_items_dict.items():
        mod = d.get("modified", 0)
        prev_mod = previous_state.get(item_id, 0)

        if item_id in previously_failed:
            retry_ids.append(item_id)
        elif item_id not in previous_state:
            new_ids.append(item_id)
        elif mod != prev_mod:
            changed_ids.append(item_id)
        else:
            unchanged_ids.append(item_id)

    deleted_ids = list(set(previous_state.keys()) - live_ids - {"_failed_ids", "_schema_version"})
    ok(f"Delta: {len(new_ids)} new | {len(changed_ids)} changed | "
       f"{len(unchanged_ids)} unchanged | {len(deleted_ids)} deleted | {len(retry_ids)} retry")

    # 4. Build cached edges
    cached_edges = []
    unchanged_set = set(unchanged_ids)
    for edge in prev_edges:
        s, t = edge.get("source"), edge.get("target")
        if s in unchanged_set and t in live_ids:
            cached_edges.append((s, t))

    # 5. Process new/changed/retry items
    all_org_ids = {iid.lower() for iid in live_items_dict.keys()}
    url_map_lower = {k: v.lower() for k, v in url_map.items()}
    items_to_process = [live_items_dict[iid] for iid in (new_ids + changed_ids + retry_ids)]

    ok(f"Extracting dependencies for {len(items_to_process)} items...")
    extraction_start = time.time()
    fresh_edges = []
    failed_ids = []
    
    global_metrics = defaultdict(lambda: {"calls": 0, "time": 0.0, "failures": 0, "expected_errors": 0})
    global_metrics["non_dict"] = {"count": 0}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                extract_dependencies,
                d["id"],
                d.get("type", "Unknown"),
                all_org_ids,
                url_map_lower,
                gis
            ): d["id"] for d in items_to_process
        }

        completed = 0
        total = len(futures)
        window_start = extraction_start
        window_count = 0

        for future in as_completed(futures):
            item_id = futures[future]
            try:
                result_id, item_edges, success, metrics = future.result()
                fresh_edges.extend(item_edges)
                
                if not success:
                    failed_ids.append(result_id)

                for endpoint in ["data", "related", "resource"]:
                    global_metrics[endpoint]["calls"] += metrics[f"{endpoint}_calls"]
                    global_metrics[endpoint]["time"] += metrics[f"{endpoint}_time"]
                    global_metrics[endpoint]["failures"] += metrics[f"{endpoint}_failures"]
                    global_metrics[endpoint]["expected_errors"] += metrics[f"{endpoint}_expected_errors"]
                
                global_metrics["non_dict"]["count"] += metrics["non_dict_responses"]

            except Exception as e:
                warn(f"Future failed for {item_id}: {e}")
                failed_ids.append(item_id)

            completed += 1
            window_count += 1

            if completed % 250 == 0 or completed == total:
                now = time.time()
                window_elapsed = now - window_start
                window_rate = window_count / window_elapsed if window_elapsed > 0 else 0
                remaining = total - completed
                eta = remaining / window_rate if window_rate > 0 else 0

                ok(f"  Progress: {completed}/{total} ({completed/total*100:.1f}%) | "
                   f"rate {window_rate:.1f} items/s | ETA {eta/60:.1f} min")
                window_start = now
                window_count = 0

    if failed_ids:
        warn(f"{len(failed_ids)} items had partial failures. Will retry next run.")

    # 6. Build ALL nodes from live inventory (with FULL rich metadata)
    ok("Building node metadata from live inventory...")
    nodes = {}
    user_cache = {}
    base_url = (getattr(gis, "url", None) or "https://www.arcgis.com").rstrip("/")
    
    for item_id, d in live_items_dict.items():
        iid_lower = item_id.lower()
        owner_username = d.get("owner", "Unknown")
        
        # Lightweight user lookup cache to get full name and email
        if owner_username not in user_cache and owner_username != "Unknown":
            try:
                u = gis.users.get(owner_username)
                user_cache[owner_username] = {
                    "name": getattr(u, "fullName", owner_username) if u else owner_username,
                    "email": getattr(u, "email", "unknown") if u else "unknown"
                }
            except Exception:
                user_cache[owner_username] = {"name": owner_username, "email": "unknown"}
        
        user_info = user_cache.get(owner_username, {"name": owner_username, "email": "unknown"})
        
        # Calculate size in MB
        size_bytes = d.get("size")
        size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes and size_bytes > 0 else None
        
        # Strip HTML and truncate description for clean display
        desc = d.get("description", "")
        if desc:
            desc = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", desc)
            desc = re.sub(r"(?s)<[^>]*>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) > 250:
                desc = desc[:247] + "..."

        nodes[iid_lower] = {
            "id": iid_lower,
            "label": d.get("title", "Unknown"),
            "type": d.get("type", "Unknown"),
            "owner": owner_username,
            "owner_name": user_info["name"],
            "owner_email": user_info["email"],
            "views": d.get("numViews", 0),
            "access": d.get("access", "private"),
            "url": d.get("url", ""),
            "modified": d.get("modified", 0),
            "created": d.get("created"),
            "tags": d.get("tags", []),
            "typeKeywords": d.get("typeKeywords", []),
            "description": desc,
            "size_mb": size_mb,
            "analysis_status": "ok"
        }
    
    for fid in failed_ids:
        fid_lower = fid.lower()
        if fid_lower in nodes:
            nodes[fid_lower]["analysis_status"] = "partial_failure"

    # 7. Size enrichment (INCREMENTAL)
    items_needing_size = [
        iid for iid, node in nodes.items()
        if node.get("type") in TYPES_WITH_SIZE and node.get("size_mb") is None
    ]
    
    if items_needing_size:
        size_map = enrich_sizes(gis, items_needing_size)
        for iid, size_data in size_map.items():
            iid_lower = iid.lower()
            if iid_lower in nodes:
                nodes[iid_lower]["size_mb"] = size_data["size_mb"]
                nodes[iid_lower]["attachments_size_mb"] = size_data["attachments_size_mb"]
                nodes[iid_lower]["size_formatted"] = format_size(size_data["size_mb"])
    else:
        ok("No items need size enrichment.")

    # 8. Build local graph
    ok("Building local dependency graph...")
    G = nx.DiGraph()
    G.add_nodes_from(nodes.keys())
    G.add_edges_from(cached_edges + fresh_edges)

    unique_edges = [{"source": u, "target": v, "type": "dependency"}
                    for u, v in G.edges() if u in nodes and v in nodes]

    # 9. Calculate stats
    ok("Computing dependency stats...")
    connected_ids = set()
    
    for item_id, node_data in nodes.items():
        if not G.has_node(item_id):
            continue

        in_deg = G.in_degree(item_id)
        out_deg = G.out_degree(item_id)

        try:
            total_deps = len(nx.descendants(G, item_id))
            total_dependents = len(nx.ancestors(G, item_id))
        except nx.NetworkXError:
            total_deps = 0
            total_dependents = 0

        node_data["dependency_info"] = {
            "immediate_dependencies": out_deg,
            "immediate_dependents": in_deg,
            "total_recursive_dependencies": total_deps,
            "total_recursive_dependents": total_dependents
        }

        is_connected = (in_deg > 0 or out_deg > 0)
        node_data["connected"] = is_connected
        if is_connected:
            connected_ids.add(item_id)
            
        item_type = node_data.get("type", "")
        if item_type in STATIC_ITEM_TYPES:
            node_data["is_unreferenced"] = False
        else:
            node_data["is_unreferenced"] = not is_connected

    # 10. High-risk items
    critical_items = sorted(
        [
            {
                "id": iid,
                "title": nodes[iid].get("label", "Unknown"),
                "type": nodes[iid].get("type", "Unknown"),
                "dependents_count": nodes[iid]["dependency_info"]["total_recursive_dependents"]
            }
            for iid in nodes
            if nodes[iid].get("dependency_info", {}).get("total_recursive_dependents", 0) > 0
        ],
        key=lambda x: x["dependents_count"],
        reverse=True
    )[:50]

    # 11. Save outputs atomically
    analysis_date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    graph_data = {
        "summary": {
            "total_items": len(nodes),
            "connected_count": len(connected_ids),
            "unreferenced_count": sum(1 for n in nodes.values() if n.get("is_unreferenced")),
            "total_relationships": len(unique_edges),
            "analysis_date": analysis_date,
            "run_timestamp": RUN_TIMESTAMP,
            "items_new": len(new_ids),
            "items_changed": len(changed_ids),
            "items_deleted": len(deleted_ids),
            "items_retry": len(retry_ids),
            "items_failed": len(failed_ids),
            "schema_version": SCHEMA_VERSION
        },
        "high_risk_items": critical_items,
        "connected_items": sorted(list(connected_ids)),
        "nodes": list(nodes.values()),
        "edges": unique_edges
    }

    atomic_write_json(OUTPUT_FILE, graph_data)
    ok(f"JSON saved: {os.path.basename(OUTPUT_FILE)}")

    # 12. Save state
    new_state = {iid: live_items_dict[iid].get("modified", 0) for iid in live_ids}
    new_state["_failed_ids"] = list(set(failed_ids))
    save_state(new_state)

    # 13. Cleanup
    cleanup_old_files(f"{FILE_BASE_NAME}_*.json", KEEP_OLD_JSON)
    cleanup_old_files(f"inventory_run_*.log", KEEP_OLD_LOGS)

    # 14. Print Metrics
    total_time = time.time() - start_total
    extraction_time = time.time() - extraction_start if 'extraction_start' in locals() else 0

    ok(f"\n{'='*70}")
    ok(f"COMPLETE in {total_time:.2f}s")
    ok(f"{'='*70}")
    ok(f"Items: {len(nodes)} | Relations: {len(unique_edges)} | Connected: {len(connected_ids)}")
    ok(f"New: {len(new_ids)} | Changed: {len(changed_ids)} | Deleted: {len(deleted_ids)}")
    ok(f"Failed (will retry next run): {len(failed_ids)}")
    ok(f"Extraction time: {extraction_time:.2f}s")
    ok(f"Schema version: {SCHEMA_VERSION}")
    
    ok("\nEndpoint Metrics:")
    for endpoint in ["data", "related", "resource"]:
        data = global_metrics[endpoint]
        if data["calls"] > 0:
            avg_time = data["time"] / data["calls"]
            ok(f"  {endpoint}: {data['calls']} calls, {data['time']:.2f}s total, "
               f"{avg_time:.3f}s avg, {data['failures']} failures, "
               f"{data['expected_errors']} expected errors")
    
    if global_metrics["non_dict"]["count"] > 0:
        warn(f"Non-dict responses encountered: {global_metrics['non_dict']['count']}")
    
    ok(f"\nLog: {os.path.basename(LOG_FILE)}")
    ok(f"{'='*70}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted. Exiting cleanly.")
    except Exception as e:
        err(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
