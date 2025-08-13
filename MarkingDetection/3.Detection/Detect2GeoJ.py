import os
from PIL import Image
from typing import List, Tuple
from pyproj import CRS
import rasterio
from rasterio.transform import Affine
import geopandas as gpd
from sahi.models.ultralytics import UltralyticsDetectionModel
from sahi.predict import get_sliced_prediction

# ---------------- CONFIGURATION ----------------

class Config:
    image_folder = r"C:/GIS_Working/ObjectDetection/DrapeYOLO/images/val"
    output_dir = r"C:/GIS_Working/ObjectDetection/DrapeOutputs"
    model_path = r"C:/GIS_Working/ObjectDetection/Scripts/runs/detect/road_markings_v2/weights/best.pt"
    buffer_geojson = r"C:/GIS_Working/ObjectDetection/ShpFiles/SFRoads2.geojson"
    tile_size = 128
    slice_overlap = 0.2
    conf_threshold = 0.3
    image_extensions = ('.png', '.jpg', '.jpeg', '.tif', '.tiff') 
    default_crs = 26918  # EPSG code

config = Config()

# ---------------- HELPERS ----------------

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
        crs = CRS.from_epsg(26918)  # Forced CRS fix
        return transform, crs

def pixel_to_coords(transform: Affine, x: float, y: float) -> Tuple[float, float]:
    return transform * (x, y)

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

def create_geojson(detections: List[dict], crs: CRS, output_path: str):
    """Create a GeoJSON file from filtered detections."""
    from shapely.geometry import Point

    geometries = []
    attributes = []

    for det in detections:
        x, y = det['abs_coords']
        geometries.append(Point(x, y))
        attributes.append({
            "class": det['category_name'],
            "confidence": round(det['score'], 4)
        })

    gdf = gpd.GeoDataFrame(attributes, geometry=geometries, crs=crs)
    gdf.to_file(output_path, driver="GeoJSON")
    print(f"\n✅ Saved GeoJSON with {len(gdf)} detections:\n{output_path}")

# ---------------- MAIN ----------------

def main():
    os.makedirs(config.output_dir, exist_ok=True)
    model = UltralyticsDetectionModel(
        model_path=config.model_path,
        confidence_threshold=config.conf_threshold
    )

    all_detections = []
    first_crs = None

    for filename in os.listdir(config.image_folder):
        if not filename.lower().endswith(config.image_extensions):
            continue

        image_path = os.path.join(config.image_folder, filename)
        print(f"🔍 Processing: {image_path}")

        image = Image.open(image_path).convert("RGBA")
        transform, crs = get_crs_and_transform(image_path)
        if first_crs is None:
            first_crs = crs
            buffer_gdf = load_buffer_geojson(config.buffer_geojson, first_crs)

        valid_tiles = get_valid_tiles(image, config.tile_size)

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
                all_detections.append((detection, transform))

    print(f"Total raw detections before filtering: {len(all_detections)}")

    final_detections = []
    for det, transform in all_detections:
        abs_x, abs_y = pixel_to_coords(transform, det['position']['x'], det['position']['y'])
        point = gpd.points_from_xy([abs_x], [abs_y])[0]
        if buffer_gdf.contains(point).any(): # type: ignore
            det['abs_coords'] = (abs_x, abs_y)
            final_detections.append(det)

    geojson_output_path = os.path.join(config.output_dir, "detections_output.geojson")
    create_geojson(final_detections, first_crs, geojson_output_path) # type: ignore

if __name__ == '__main__':
    main()
