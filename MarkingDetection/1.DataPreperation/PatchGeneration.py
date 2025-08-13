import os
from PIL import Image

# --- Configuration ---
DATASET_ROOT = r'C:\GIS_Working\ObjectDetection\DrapeYOLO' # main YOLO dataset root

# Directories for existing large images and labels
SOURCE_IMAGES_DIR = os.path.join(DATASET_ROOT, 'images', 'val') 
SOURCE_LABELS_DIR = os.path.join(DATASET_ROOT, 'labels', 'val')

# Output root for the new object-centric patches
OUTPUT_PATCHES_ROOT = r'C:\GIS_Working\ObjectDetection\DrapePatched' # New root for patches

# Desired size for each output patch (e.g., 128x128 pixels)
PATCH_SIZE = 128 

# Padding color (BGR for OpenCV, or RGB for PIL - let's use a neutral gray)
# PIL uses RGB, so (128, 128, 128) for gray
PAD_COLOR = (128, 128, 128) 

# --- Create output directories ---
OUTPUT_IMAGES_DIR = os.path.join(OUTPUT_PATCHES_ROOT, 'images', 'val') # Adjust 'train'/'val' as needed
OUTPUT_LABELS_DIR = os.path.join(OUTPUT_PATCHES_ROOT, 'labels', 'val') # Adjust 'train'/'val' as needed

os.makedirs(OUTPUT_IMAGES_DIR, exist_ok=True)
os.makedirs(OUTPUT_LABELS_DIR, exist_ok=True)

print(f"Reading original images from: {SOURCE_IMAGES_DIR}")
print(f"Reading original labels from: {SOURCE_LABELS_DIR}")
print(f"Saving new patches to: {OUTPUT_IMAGES_DIR}")
print(f"Saving new patch labels to: {OUTPUT_LABELS_DIR}")
print(f"Each patch size: {PATCH_SIZE}x{PATCH_SIZE} pixels")
print("-" * 50)

processed_objects_count = 0

# --- Function to convert YOLO (normalized) to Pascal VOC (absolute) ---
def yolo_to_abs(x_center, y_center, width, height, img_w, img_h):
    xmin = int((x_center - width / 2) * img_w)
    ymin = int((y_center - height / 2) * img_h)
    xmax = int((x_center + width / 2) * img_w)
    ymax = int((y_center + height / 2) * img_h)
    return xmin, ymin, xmax, ymax

# --- Function to convert Pascal VOC (absolute) to YOLO (normalized) ---
def abs_to_yolo(xmin, ymin, xmax, ymax, img_w, img_h):
    x_center = (xmin + xmax) / 2.0 / img_w
    y_center = (ymin + ymax) / 2.0 / img_h
    width = (xmax - xmin) / img_w
    height = (ymax - ymin) / img_h
    return x_center, y_center, width, height

# --- Process each original image ---
for img_filename in os.listdir(SOURCE_IMAGES_DIR):
    if not img_filename.lower().endswith('.png'):
        continue

    basename = os.path.splitext(img_filename)[0]
    img_path = os.path.join(SOURCE_IMAGES_DIR, img_filename)
    label_path = os.path.join(SOURCE_LABELS_DIR, basename + '.txt')

    if not os.path.exists(label_path):
        print(f"Warning: No label file found for {img_filename}. Skipping.")
        continue

    try:
        original_img = Image.open(img_path).convert("RGB") # Ensure 3 channels
        img_w, img_h = original_img.size
    except Exception as e:
        print(f"Error opening image {img_filename}: {e}. Skipping.")
        continue

    # Read YOLO labels
    objects = []
    with open(label_path, 'r') as f:
        for line in f:
            parts = list(map(float, line.strip().split()))
            class_id = int(parts[0])
            # Convert normalized YOLO to absolute pixels in original image
            xmin, ymin, xmax, ymax = yolo_to_abs(parts[1], parts[2], parts[3], parts[4], img_w, img_h)
            objects.append({'class_id': class_id, 'bbox': (xmin, ymin, xmax, ymax)})

    # Process each object in the current image
    for obj_idx, obj in enumerate(objects):
        class_id = obj['class_id']
        obj_xmin, obj_ymin, obj_xmax, obj_ymax = obj['bbox']

        # Calculate center of the object's bounding box
        obj_center_x = (obj_xmin + obj_xmax) / 2
        obj_center_y = (obj_ymin + obj_ymax) / 2

        # Calculate the top-left corner of the desired PATCH_SIZE centered around the object
        patch_xmin = int(obj_center_x - PATCH_SIZE / 2)
        patch_ymin = int(obj_center_y - PATCH_SIZE / 2)
        patch_xmax = patch_xmin + PATCH_SIZE
        patch_ymax = patch_ymin + PATCH_SIZE

        # Create a new blank image for the patch with padding color
        padded_patch = Image.new('RGB', (PATCH_SIZE, PATCH_SIZE), PAD_COLOR)

        # Calculate actual crop region and paste onto the padded patch
        # This handles cases where the patch goes out of bounds of the original image
        
        # Define the region to crop from original image (in original image coordinates)
        crop_left = max(0, patch_xmin)
        crop_top = max(0, patch_ymin)
        crop_right = min(img_w, patch_xmax)
        crop_bottom = min(img_h, patch_ymax)

        # Define where to paste this cropped region onto the new (padded) patch
        paste_x_on_patch = 0 if patch_xmin >= 0 else -patch_xmin
        paste_y_on_patch = 0 if patch_ymin >= 0 else -patch_ymin

        if crop_right > crop_left and crop_bottom > crop_top: # Ensure valid crop area
            cropped_region = original_img.crop((crop_left, crop_top, crop_right, crop_bottom))
            padded_patch.paste(cropped_region, (paste_x_on_patch, paste_y_on_patch))

        # --- Generate new label for this patch ---
        # The object's bounding box coordinates relative to the new patch
        new_obj_xmin = obj_xmin - patch_xmin
        new_obj_ymin = obj_ymin - patch_ymin
        new_obj_xmax = obj_xmax - patch_xmin
        new_obj_ymax = obj_ymax - patch_ymin

        # Clamp new bbox coordinates to patch boundaries (0 to PATCH_SIZE)
        new_obj_xmin = max(0, new_obj_xmin)
        new_obj_ymin = max(0, new_obj_ymin)
        new_obj_xmax = min(PATCH_SIZE, new_obj_xmax)
        new_obj_ymax = min(PATCH_SIZE, new_obj_ymax)

        # Convert the new absolute bbox to YOLO normalized format for the PATCH_SIZE
        norm_x_center, norm_y_center, norm_width, norm_height = abs_to_yolo(
            new_obj_xmin, new_obj_ymin, new_obj_xmax, new_obj_ymax, PATCH_SIZE, PATCH_SIZE
        )
        
        # Create a unique filename for the patch
        new_img_filename = f"{basename}_obj{obj_idx:03d}.png"
        new_label_filename = f"{basename}_obj{obj_idx:03d}.txt"

        # Save the new patch image
        output_img_path = os.path.join(OUTPUT_IMAGES_DIR, new_img_filename)
        padded_patch.save(output_img_path)

        # Save the new label file
        output_label_path = os.path.join(OUTPUT_LABELS_DIR, new_label_filename)
        with open(output_label_path, 'w') as out_f:
            out_f.write(f"{class_id} {norm_x_center} {norm_y_center} {norm_width} {norm_height}\n")
        
        processed_objects_count += 1
        print(f"Generated patch for '{basename}', object {obj_idx+1}. Total patches: {processed_objects_count}")

print("\n--- Patch Generation Complete ---")
print(f"Total objects converted to patches: {processed_objects_count}")
print(f"Patches saved to: {OUTPUT_PATCHES_ROOT}")