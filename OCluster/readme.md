# AGOL Content Galaxy 🌌

**Visualize and trace deep dependencies between ArcGIS Portal items, from Feature Layers to Apps.**

AGOL Content Galaxy solves the "where is this used?" problem. By crawling your portal's internal JSON, it maps relationships that the standard ArcGIS interface often misses—such as layers tucked inside Web Maps, which are then embedded in Experience Builder apps.

---

## 🚀 How It Works

The project consists of two distinct components:

1. **The Crawler (`crawler.py`):**
   - Authenticates with your GIS (ArcGIS Online or Enterprise).
   - Performs a recursive scan of all items.
   - Parses item JSON to find "hidden" dependencies.
   - Outputs `content_graph.json` in the project folder.

2. **The Galaxy (`index.html`):**
   - Loads `content_graph.json`.
   - Renders an interactive force-directed "Galaxy" of your portal assets.
   - Provides "Kinetic Lineage" to trace upstream and downstream dependencies.

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

*This will generate `content_graph.json` in your local folder.*

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

## 🎨 Visual Guide

| Asset Type   | Color     | Type Examples                        |
| ------------ | --------- | ------------------------------------ |
| **Features** | 🟢 Green  | Feature Layers / Services            |
| **Web Maps** | 🔵 Blue   | Maps organizing feature data         |
| **Apps**     | 🟣 Purple | Dashboards, Experience Builder       |
| **Other**    | 🟡 Gold   | Utilities, Notebooks, orphaned files |

---

## ⌨️ Interface Controls

* **Scroll/Pinch:** Zoom in to see individual assets or out for the "Galaxy" view.
* **Drag:** Move the entire galaxy or individual nodes.
* **Search:** Use the top-right search bar to find an asset by name.
* **Click Node:** Enters **Focus Mode**. It isolates the "Kinetic Lineage" of that asset, showing exactly what feeds into it (Upstream) and what it powers (Downstream).
* **Reset:** Returns the galaxy to its default orbital rotation.

---

## 📝 Technical Notes

* **Recursive Parsing:** The crawler uses a recursive `extract_ids_from_dict` function to find 32-character ArcGIS IDs nested at any depth within item JSON.
* **Orphan Filtering:** The script automatically excludes items with zero connections to keep the visualization clean and meaningful.
* **Performance:** The D3 engine is optimized for up to ~5,000 nodes. For larger portals, consider using the `max_items` filter in the Python script.

