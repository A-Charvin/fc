import os
from PIL import Image
from typing import List, Tuple
from pyproj import CRS
import rasterio
from rasterio.transform import Affine
import geopandas as gpd
from sahi.models.ultralytics import UltralyticsDetectionModel
from sahi.predict import get_sliced_prediction

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Patch
from pathlib import Path
import numpy as np

# --------------------------- CONFIG ---------------------------

class Config:
    image_path = r"C:/GIS_Working/ObjectDetection/DrapeYOLO/images/train/clipped.png"
    output_dir = r"C:/GIS_Working/ObjectDetection/DrapeOutputs"
    model_path = r"C:/GIS_Working/ObjectDetection/Scripts/runs/detect/road_markings_v2/weights/best.pt"
    buffer_geojson = r"C:/GIS_Working/ObjectDetection/ShpFiles/SFRoads2.geojson"
    tile_size = 128
    slice_overlap = 0.2
    conf_threshold = 0.3
    category_names = ['StopBar', 'TurnArrow', 'CrossWalk', 'Diamond', 'CycleLane', 'Cross']  # our categories, Change it based on trainging Data
config = Config()

CLASS_COLORS = {
    'StopBar': "#1AE413",      # Green
    'TurnArrow': "#D9FF00",    # Yellow 
    'CrossWalk': "#00FFFF",    # Cyan
    'Diamond': "#FF4800",      # Red
    'CycleLane': "#1100FF",    # Blue
    'Cross': "#F700FF",        # Magenta
    'default': '#FFFFFF'       # White for unknown classes
}

# --------------------------- HELPERS ---------------------------

def get_valid_tiles(image: Image.Image, tile_size: int) -> List[Tuple[int, int]]:
    valid_tiles = []
    width, height = image.size
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            tile = image.crop((x, y, x + tile_size, y + tile_size))
            if tile.getbbox() is not None:
                valid_tiles.append((x, y))
    return valid_tiles

def get_crs_and_transform(img_path: str) -> Tuple[Affine, CRS]:
    with rasterio.open(img_path) as src:
        transform = src.transform
        crs = CRS.from_epsg(26918)  # Forcing our CRS
        return transform, crs

def pixel_to_coords(transform: Affine, x: float, y: float) -> Tuple[float, float]:
    xp, yp = transform * (x, y) # type: ignore
    return xp, yp

def load_buffer_geojson(path: str, target_crs: CRS) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        print("Buffer GeoJSON missing CRS, setting to EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(target_crs)

def filter_detections_within_buffer(predictions: List[dict], transform: Affine, buffer_gdf: gpd.GeoDataFrame) -> List[dict]:
    kept = []
    for pred in predictions:
        xcenter, ycenter = pred['position']['x'], pred['position']['y']
        abs_x, abs_y = pixel_to_coords(transform, xcenter, ycenter)
        point = gpd.points_from_xy([abs_x], [abs_y])[0]
        if buffer_gdf.contains(point).any():
            pred['abs_coords'] = (abs_x, abs_y)
            kept.append(pred)
    return kept

# ------------------ Matplotlib Visualization Functions -------------------

def matplotlib_point_visualization(detections, image_path, output_path, class_colors, point_size=6, legend_font_size=12):
    """Visualize detections with points, opacity by confidence, and legend."""
    image = plt.imread(image_path)
    if image.dtype == np.float32:
        image = (image * 255).astype(np.uint8)

    # Group detections by class
    class_counts = {}
    detection_points = {}
    for det in detections:
        cls = det['category_name']
        x = det['position']['x']
        y = det['position']['y']
        conf = det['score']
        detection_points.setdefault(cls, []).append((x, y, conf))
        class_counts[cls] = class_counts.get(cls, 0) + 1

    fig, ax = plt.subplots(figsize=(16, 12))
    ax.imshow(image)
    ax.set_xlim(0, image.shape[1])
    ax.set_ylim(image.shape[0], 0)  # Flip y-axis

    legend_elements = []
    for cls, points in detection_points.items():
        color = class_colors.get(cls, class_colors.get('default', 'white'))
        for x, y, conf in points:
            alpha = max(0.7, conf)  # min opacity 0.7 for visibility
            circ = Circle((x, y), radius=point_size, color=color, alpha=alpha,
                          linewidth=2, edgecolor='white', zorder=10)
            ax.add_patch(circ)
        legend_elements.append(Patch(color=color, label=f"{cls} ({class_counts[cls]})"))

    ax.legend(handles=legend_elements, loc='upper right',
              fontsize=legend_font_size, framealpha=0.9, fancybox=True, shadow=True)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Detection Results - {Path(image_path).name}\nTotal Detections: {len(detections)}",
                 fontsize=16, fontweight='bold')

    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()

def matplotlib_detailed_visualization(detections, image_path, output_path, class_colors, point_size=6, legend_font_size=12):
    """Visualize detections with points, confidence labels, and legend."""
    image = plt.imread(image_path)
    if image.dtype == np.float32:
        image = (image * 255).astype(np.uint8)

    class_counts = {}
    fig, ax = plt.subplots(figsize=(20, 16))
    ax.imshow(image)
    ax.set_xlim(0, image.shape[1])
    ax.set_ylim(image.shape[0], 0)  # Flip y-axis

    for det in detections:
        cls = det['category_name']
        x = det['position']['x']
        y = det['position']['y']
        conf = det['score']
        color = class_colors.get(cls, class_colors.get('default', 'white'))

        circ = Circle((x, y), radius=point_size + 2, color=color, alpha=0.8,
                      linewidth=3, edgecolor='white', zorder=10)
        ax.add_patch(circ)

        ax.text(x + point_size + 5, y - point_size - 5,
                f"{conf:.2f}", fontsize=8, color='white',
                bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.7),
                zorder=11)

        class_counts[cls] = class_counts.get(cls, 0) + 1

    legend_elements = [Patch(color=class_colors.get(cls, class_colors.get('default', 'white')),
                            label=f"{cls} ({count})")
                       for cls, count in sorted(class_counts.items())]

    ax.legend(handles=legend_elements, loc='upper right',
              fontsize=legend_font_size, framealpha=0.9, fancybox=True, shadow=True)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Detailed Detection Results with Confidence Values\n{Path(image_path).name}",
                 fontsize=18, fontweight='bold')

    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()

# --------------------------- MAIN ---------------------------

def main():
    image = Image.open(config.image_path).convert("RGBA")
    transform, crs = get_crs_and_transform(config.image_path)
    print(f"Using CRS: {crs.to_string()}")

    buffer_gdf = load_buffer_geojson(config.buffer_geojson, crs)
    print(f"Buffer GeoDataFrame CRS: {buffer_gdf.crs}")

    valid_tiles = get_valid_tiles(image, config.tile_size)
    model = UltralyticsDetectionModel(model_path=config.model_path, confidence_threshold=config.conf_threshold)
    all_detections = []

    for tile_x, tile_y in valid_tiles:
        tile = image.crop((tile_x, tile_y, tile_x + config.tile_size, tile_y + config.tile_size)).convert("RGB")
        result = get_sliced_prediction(
            image=tile,
            detection_model=model,
            slice_height=config.tile_size,
            slice_width=config.tile_size,
            overlap_height_ratio=config.slice_overlap,
            overlap_width_ratio=config.slice_overlap,
            verbose=0
        )
        for obj in result.object_prediction_list:
            pred = obj.to_coco_prediction()
            x_center = pred.bbox[0] + tile_x + pred.bbox[2] / 2
            y_center = pred.bbox[1] + tile_y + pred.bbox[3] / 2
            detection = {
                'bbox': pred.bbox,
                'score': pred.score,
                'category_id': pred.category_id,
                'category_name': obj.category.name,
                'position': {'x': x_center, 'y': y_center},
            }
            all_detections.append(detection)

    filtered = filter_detections_within_buffer(all_detections, transform, buffer_gdf)

    os.makedirs(config.output_dir, exist_ok=True)

    # Matplotlib styled visualizations
    points_vis_path = os.path.join(config.output_dir, "detections_matplotlib_points.png")
    matplotlib_point_visualization(filtered, config.image_path, points_vis_path, CLASS_COLORS)

    detailed_vis_path = os.path.join(config.output_dir, "detections_matplotlib_detailed.png")
    matplotlib_detailed_visualization(filtered, config.image_path, detailed_vis_path, CLASS_COLORS)

    print(f"Saved matplotlib styled point visualization: {points_vis_path}")
    print(f"Saved matplotlib styled detailed visualization: {detailed_vis_path}")

if __name__ == '__main__':
    main()
