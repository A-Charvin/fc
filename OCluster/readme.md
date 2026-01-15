# AGOL Content Galaxy 🌌

**Visualize and trace deep dependencies between ArcGIS Portal items, from Feature Layers to Apps.**

AGOL Content Galaxy solves the "where is this used?" problem. By crawling your portal's internal JSON and performing recursive dependency analysis,
it maps relationships that the standard ArcGIS interface often misses—such as layers tucked inside Web Maps, which are then embedded in Experience Builder apps.

---

## 🚀 How It Works

The project consists of two distinct components:

1. **The Crawler (`crawler.py`):**
* Authenticates with your GIS (ArcGIS Online or Enterprise).
* Performs a recursive scan of all items using the `ItemGraph` engine.
* Calculates **Blast Radius** (how many items break if this is deleted) and **Dependencies** (how many items this relies on).
* Outputs `content_audit_graph.json` in the project folder.


2. **The Galaxy (`index.html`):**
* Renders an interactive force-directed "Galaxy" using D3.js.
* Provides **Kinetic Lineage** to trace upstream and downstream paths.
* Features a **HUD Sidebar** with deep-drilldown relationship trees.


---

## 🛠️ Setup & Usage

### 1. Generate the Data

This script is intended to be run from a **cloned ArcGIS Pro Python environment**, which already includes ArcPy and the ArcGIS API for Python.

**Recommended setup:**

1. Open **ArcGIS Pro**
2. Navigate to **Settings → Python → Manage Environments**
3. Clone the default `arcgispro-py3` environment
4. Note the path to the cloned environment’s Python executable

**Using your preferred IDE (VS Code):**

- Open **VS Code**
- Select the cloned ArcGIS Pro environment as your Python interpreter  
  (`Ctrl + Shift + P` → *Python: Select Interpreter*)
- Choose the Python executable from the cloned ArcGIS Pro environment
- Run the script directly from VS Code

> Using the cloned ArcGIS Pro environment inside your IDE ensures full compatibility with ArcPy, the ArcGIS API for Python, and your authenticated portal session.

Run the crawler. The script is configured to use `GIS("home")` (ideal for ArcGIS Pro or Notebooks), but can be modified for specific credentials.

```bash
python crawler.py

```

*This will now generate both `content_audit_graph.json` (for the Galaxy) and `dependency_network.gml` (for external analysis).*

---

### 2. Launch the Visualization

Because the frontend loads a local JSON file, you must run it via a web server (to avoid CORS browser security blocks).

**Option A (Quickest):**

```bash
# In the project folder, run:
python -m http.server 8000

```

Then visit `http://localhost:8000` in your browser.

**Option B (Deployment):**
Upload `index.html` and `content_graph.json` to any web server (IIS, GitHub Pages, or an S3 bucket).

---

## 🎨 Visual Guide & Metrics

| Asset Type | Color | Description |
| --- | --- | --- |
| **Features** | 🟢 Green | Feature Layers / Services |
| **Web Maps** | 🔵 Blue | Maps organizing feature data |
| **Apps** | 🟣 Purple | Dashboards, Experience Builder, Web AppBuilder |
| **Space Junk** | 🔴 Red (Glow) | **Abandoned Nodes:** Items with 0 connections floating in the void. |

---
### 📊 Advanced Metrics in Sidebar

* **Blast Radius:** The total count of recursive dependents. A high number means many apps/maps will break if this item is modified.
* **Dependencies:** The total count of items this asset requires to function properly.
* **View Count:** Real-time popularity data pulled from AGOL.

---

## ⌨️ Interface Controls

* **Scroll/Pinch:** Zoom from the "Galaxy" view (0.045x) down to individual asset labels.
* **Click Node:** Enters **Focus Mode**. Isolates the lineage and opens the **Relationship Hierarchy** tree.
* **Relationship Tree:** * `▲` **Provider:** An item this asset relies on (Upstream).
* `▼` **Consumer:** An item that consumes this asset (Downstream).
* **Filter by Type:** Click the legend items to dim everything except the selected category.
* **Search:** Find any asset by name to jump directly to its location in the galaxy.

---

## 🛰️ Data Exports

The crawler now generates two distinct output files to support different workflows:

1. **`content_audit_graph.json`**: Optimized for the Web Galaxy frontend. Includes UI-specific metadata like node colors, blast radius metrics, and orbital positions.
2. **`dependency_network.gml`**: A standardized XML-based geography file. This allows you to import the portal's dependency "geography" into:
* **Gephi**: For advanced network topology analysis.
* **ArcGIS Pro / QGIS**: To treat the dependency graph as a formal spatial layer.
* **NetworkX**: For programmatic graph theory calculations in Python.

---

## 📝 Technical Notes

* **Recursive Analysis:** Unlike standard crawlers, this project calculates "recursive blast radius," meaning it knows if a Feature Layer is used in a Map that is used in a Dashboard that is embedded in a Hub Site.
* **GML Schema:** The GML output follows the standard `node` and `edge` schema, preserving all AGOL metadata (Item ID, Type, Owner) as attributes within the XML structure.
* **D3 Engine:** Uses a high-performance force simulation with custom collision detection to prevent node overlapping.
* **Authentication:** Uses `GIS("home")` by default to leverage your existing ArcGIS Pro credentials.

---
