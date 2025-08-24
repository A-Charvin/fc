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
    point_size = 6
    category_names = ['StopBar', 'TurnArrow', 'CrossWalk', 'Diamond', 'CycleLane', 'Cross']  # our categories, Change it based on trainging Data

config = Config()

CLASS_COLORS = {
    'StopBar': "#1AE413", 'TurnArrow': "#D9FF00", 'CrossWalk': "#00FFFF",
    'Diamond': "#FF4800", 'CycleLane': "#1100FF", 'Cross': "#F700FF", 'default': '#FFFFFF'
}

# --------------------------- HELPERS ---------------------------

def get_crs_and_transform(img_path: str) -> tuple[Affine, CRS]:
    """Get transform and CRS from raster image."""
    with rasterio.open(img_path) as src:
        return src.transform, CRS.from_epsg(26918)  # Using your target CRS

def pixel_to_coords(transform: Affine, x: float, y: float) -> tuple[float, float]:
    """Convert pixel coordinates to geographic coordinates."""
    return transform * (x, y)

def load_buffer_geojson(path: str, target_crs: CRS) -> gpd.GeoDataFrame:
    """Load and reproject buffer geometry."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        print("Buffer GeoJSON missing CRS, setting to EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(target_crs)

def filter_detections_within_buffer(detections: list, transform: Affine, buffer_gdf: gpd.GeoDataFrame) -> list:
    """Filter detections to only those within buffer geometry."""
    filtered = []
    for det in detections:
        x, y = det['position']['x'], det['position']['y']
        abs_x, abs_y = pixel_to_coords(transform, x, y)
        point = gpd.points_from_xy([abs_x], [abs_y])[0]
        
        if buffer_gdf.contains(point).any():
            det['abs_coords'] = (abs_x, abs_y)
            filtered.append(det)
    
    return filtered

def create_visualization(detections: list, image_path: str, output_path: str, 
                        detailed: bool = False) -> None:
    """Create matplotlib visualization with points."""
    image = plt.imread(image_path)
    if image.dtype == np.float32:
        image = (image * 255).astype(np.uint8)

    class_counts = {}
    detection_data = {}
    
    for det in detections:
        cls = det['category_name']
        x, y, conf = det['position']['x'], det['position']['y'], det['score']
        
        detection_data.setdefault(cls, []).append((x, y, conf))
        class_counts[cls] = class_counts.get(cls, 0) + 1

    # Create plot
    fig, ax = plt.subplots(figsize=(20, 16) if detailed else (16, 12))
    ax.imshow(image)
    ax.set_xlim(0, image.shape[1])
    ax.set_ylim(image.shape[0], 0)

    # Plot detections
    legend_elements = []
    for cls, points in detection_data.items():
        color = CLASS_COLORS.get(cls, CLASS_COLORS['default'])
        
        for x, y, conf in points:
            radius = config.point_size + (2 if detailed else 0)
            alpha = max(0.7, conf) if not detailed else 0.8
            linewidth = 3 if detailed else 2
            
            circle = Circle((x, y), radius=radius, color=color, alpha=alpha,
                          linewidth=linewidth, edgecolor='white', zorder=10)
            ax.add_patch(circle)
            
            if detailed:
                ax.text(x + radius + 5, y - radius - 5, f"{conf:.2f}", fontsize=8, color='white',
                       bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.7), zorder=11)
        
        legend_elements.append(Patch(color=color, label=f"{cls} ({class_counts[cls]})"))

    # Styling
    title = f"{'Detailed ' if detailed else ''}Detection Results"
    if detailed:
        title += " with Confidence Values"
    title += f"\n{Path(image_path).name} - Total: {len(detections)}"
    
    ax.set_title(title, fontsize=18 if detailed else 16, fontweight='bold', pad=20)
    ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98),
             fontsize=12, framealpha=0.9, fancybox=True, shadow=True)
    
    if not detailed:
        ax.text(0.02, 0.02, "Point Opacity = Confidence Level", transform=ax.transAxes,
               fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8))
    
    ax.set_xticks([])
    ax.set_yticks([])
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()

# --------------------------- MAIN ---------------------------

def main():
    print(f"Processing image: {config.image_path}")
    
    # Load image and spatial info
    image = Image.open(config.image_path).convert("RGB")  # SAHI expects RGB
    transform, crs = get_crs_and_transform(config.image_path)
    print(f"Using CRS: {crs.to_string()}")
    
    # Load buffer geometry
    buffer_gdf = load_buffer_geojson(config.buffer_geojson, crs)
    print(f"Buffer GeoDataFrame CRS: {buffer_gdf.crs}")
    
    # Initialize model
    model = UltralyticsDetectionModel(
        model_path=config.model_path, 
        confidence_threshold=config.conf_threshold
    )
    print(f"Model loaded with confidence threshold: {config.conf_threshold}")
    
    # Run SAHI detection on FULL image (not tiles!)
    print("Running sliced prediction...")
    result = get_sliced_prediction(
        image=image,  # Full image - SAHI handles slicing internally
        detection_model=model,
        slice_height=config.slice_size,
        slice_width=config.slice_size,
        overlap_height_ratio=config.slice_overlap,
        overlap_width_ratio=config.slice_overlap,
        verbose=1
    )
    
    # Convert SAHI results to our format
    all_detections = []
    for obj in result.object_prediction_list:
        bbox = obj.bbox.to_voc_bbox()  # [xmin, ymin, xmax, ymax]
        x_center = (bbox[0] + bbox[2]) / 2
        y_center = (bbox[1] + bbox[3]) / 2
        
        detection = {
            'bbox': bbox,
            'score': obj.score.value,
            'category_id': obj.category.id,
            'category_name': obj.category.name,
            'position': {'x': x_center, 'y': y_center},
        }
        all_detections.append(detection)
    
    print(f"Total detections before filtering: {len(all_detections)}")
    
    # Filter by buffer geometry
    filtered_detections = filter_detections_within_buffer(all_detections, transform, buffer_gdf)
    print(f"Detections within buffer: {len(filtered_detections)}")
    
    # Create output directory
    os.makedirs(config.output_dir, exist_ok=True)
    
    # Generate visualizations
    points_path = os.path.join(config.output_dir, "detections_points.png")
    detailed_path = os.path.join(config.output_dir, "detections_detailed.png")
    
    create_visualization(filtered_detections, config.image_path, points_path, detailed=False)
    create_visualization(filtered_detections, config.image_path, detailed_path, detailed=True)
    
    # Print summary
    class_counts = {}
    for det in filtered_detections:
        cls = det['category_name']
        class_counts[cls] = class_counts.get(cls, 0) + 1
    
    print("\n" + "="*50)
    print("DETECTION SUMMARY")
    print("="*50)
    for cls, count in sorted(class_counts.items()):
        color = CLASS_COLORS.get(cls, CLASS_COLORS['default'])
        print(f"{cls:12s} ({color}): {count:3d} detections")
    
    confidences = [det['score'] for det in filtered_detections]
    if confidences:
        print(f"\nTotal: {len(filtered_detections)} | Confidence - "
              f"Mean: {np.mean(confidences):.3f}, Min: {np.min(confidences):.3f}, "
              f"Max: {np.max(confidences):.3f}")
    
    print(f"\nOutputs saved:")
    print(f"Points visualization: {points_path}")
    print(f"Detailed visualization: {detailed_path}")

if __name__ == '__main__':
    main()
