import os
from PIL import Image

# --- Configuration ---
DATASET_ROOT = r'C:\GIS_Working\ObjectDetection\DrapeYOLO' # main YOLO dataset root
OUTPUT_PATCHES_ROOT = r'C:\GIS_Working\ObjectDetection\DrapeYOLO_Patches' # Output Location

PATCH_SIZE = 128
OVERLAP = 0.2  # 20% overlap
VALID_SPLITS = ['train', 'val', 'test']  # process these if present

# --- Conversions ---
def yolo_to_abs(x_center, y_center, width, height, img_w, img_h):
    xmin = int((x_center - width / 2) * img_w)
    ymin = int((y_center - height / 2) * img_h)
    xmax = int((x_center + width / 2) * img_w)
    ymax = int((y_center + height / 2) * img_h)
    return xmin, ymin, xmax, ymax

def abs_to_yolo(xmin, ymin, xmax, ymax, img_w, img_h):
    x_center = (xmin + xmax) / 2.0 / img_w
    y_center = (ymin + ymax) / 2.0 / img_h
    width = (xmax - xmin) / img_w
    height = (ymax - ymin) / img_h
    return x_center, y_center, width, height

# --- Sliding patch generator ---
def process_split(split_name):
    source_images_dir = os.path.join(DATASET_ROOT, 'images', split_name)
    source_labels_dir = os.path.join(DATASET_ROOT, 'labels', split_name)
    output_images_dir = os.path.join(OUTPUT_PATCHES_ROOT, 'images', split_name)
    output_labels_dir = os.path.join(OUTPUT_PATCHES_ROOT, 'labels', split_name)

    if not os.path.exists(source_images_dir):
        print(f"⚠️  No '{split_name}' split found at {source_images_dir}, skipping...")
        return 0

    os.makedirs(output_images_dir, exist_ok=True)
    os.makedirs(output_labels_dir, exist_ok=True)

    stride = int(PATCH_SIZE * (1 - OVERLAP))
    processed_patches_count = 0

    print(f"\n=== Processing split: {split_name} ===")
    print(f"Images: {source_images_dir}")
    print(f"Labels: {source_labels_dir}")
    print(f"Output → {output_images_dir}")

    for img_filename in os.listdir(source_images_dir):
        if not img_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue

        basename = os.path.splitext(img_filename)[0]
        img_path = os.path.join(source_images_dir, img_filename)
        label_path = os.path.join(source_labels_dir, basename + '.txt')

        if not os.path.exists(label_path):
            print(f"⚠️  No label for {img_filename}, skipping.")
            continue

        try:
            original_img = Image.open(img_path).convert("RGB")
            img_w, img_h = original_img.size
        except Exception as e:
            print(f"❌ Error opening {img_filename}: {e}")
            continue

        # Read YOLO labels → absolute coords
        objects = []
        with open(label_path, 'r') as f:
            for line in f:
                parts = list(map(float, line.strip().split()))
                class_id = int(parts[0])
                xmin, ymin, xmax, ymax = yolo_to_abs(parts[1], parts[2], parts[3], parts[4], img_w, img_h)
                objects.append({'class_id': class_id, 'bbox': (xmin, ymin, xmax, ymax)})

        patch_idx = 0
        for top in range(0, img_h, stride):
            for left in range(0, img_w, stride):
                right = min(left + PATCH_SIZE, img_w)
                bottom = min(top + PATCH_SIZE, img_h)

                # Extract patch
                patch = original_img.crop((left, top, right, bottom))

                # Collect objects inside patch
                patch_labels = []
                for obj in objects:
                    oxmin, oymin, oxmax, oymax = obj['bbox']

                    # Intersection check
                    if oxmax <= left or oxmin >= right or oymax <= top or oymin >= bottom:
                        continue

                    # Clamp bbox to patch boundaries
                    new_xmin = max(oxmin, left) - left
                    new_ymin = max(oymin, top) - top
                    new_xmax = min(oxmax, right) - left
                    new_ymax = min(oymax, bottom) - top

                    if new_xmax <= new_xmin or new_ymax <= new_ymin:
                        continue

                    # Normalize for YOLO
                    x_c, y_c, w, h = abs_to_yolo(
                        new_xmin, new_ymin, new_xmax, new_ymax,
                        right - left, bottom - top
                    )
                    patch_labels.append((obj['class_id'], x_c, y_c, w, h))

                # Skip empty patches
                if not patch_labels:
                    continue

                # Save patch image as png section commented out to change into jpeg
                # patch_name = f"{basename}_patch{patch_idx:04d}.png"
                # patch.save(os.path.join(output_images_dir, patch_name))

                # Save patch images as jpg
                patch_name = f"{basename}_patch{patch_idx:04d}.jpg"  # Changed to .jpg
                patch.save(os.path.join(output_images_dir, patch_name), "JPEG", quality=95)

                # Save patch labels
                with open(os.path.join(output_labels_dir, f"{basename}_patch{patch_idx:04d}.txt"), 'w') as out_f:
                    for lbl in patch_labels:
                        out_f.write(f"{lbl[0]} {lbl[1]:.6f} {lbl[2]:.6f} {lbl[3]:.6f} {lbl[4]:.6f}\n")

                processed_patches_count += 1
                patch_idx += 1

        print(f"✔ {img_filename} → {patch_idx} patches")

    print(f"=== Finished {split_name} | Total patches: {processed_patches_count} ===")
    return processed_patches_count


# --- Run for all splits ---
total = 0
for split in VALID_SPLITS:
    total += process_split(split)

print("\n--- Sliding Patch Generation Complete ---")
print(f"Grand total patches generated: {total}")
print(f"Saved under: {OUTPUT_PATCHES_ROOT}")
