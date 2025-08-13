import os
import shutil
import random

# --- Configuration ---
DATASET_ROOT = r'I:\Drape\DrapeYOLO'

SOURCE_IMAGES_TRAIN_DIR = os.path.join(DATASET_ROOT, 'images', 'train')
SOURCE_LABELS_TRAIN_DIR = os.path.join(DATASET_ROOT, 'labels', 'train')

DEST_IMAGES_VAL_DIR = os.path.join(DATASET_ROOT, 'images', 'val')
DEST_LABELS_VAL_DIR = os.path.join(DATASET_ROOT, 'labels', 'val')

# Percentage of data to move to the validation set (e.g., 0.20 for 20%)
VAL_RATIO = 0.20

# --- Create destination directories if they don't exist ---
os.makedirs(DEST_IMAGES_VAL_DIR, exist_ok=True)
os.makedirs(DEST_LABELS_VAL_DIR, exist_ok=True)

print(f"Dataset root: {DATASET_ROOT}")
print(f"Source train images: {SOURCE_IMAGES_TRAIN_DIR}")
print(f"Source train labels: {SOURCE_LABELS_TRAIN_DIR}")
print(f"Destination val images: {DEST_IMAGES_VAL_DIR}")
print(f"Destination val labels: {DEST_LABELS_VAL_DIR}")
print(f"Validation ratio: {VAL_RATIO * 100:.0f}%")

# --- Gather all valid image basenames ---
image_basenames = []
for filename in os.listdir(SOURCE_IMAGES_TRAIN_DIR):
    if filename.lower().endswith('.png'):
        basename = os.path.splitext(filename)[0] # Get filename without .png
        
        # Check if corresponding label file exists
        label_path = os.path.join(SOURCE_LABELS_TRAIN_DIR, basename + '.txt')
        if os.path.exists(label_path):
            image_basenames.append(basename)
        else:
            print(f"Warning: Image '{filename}' found, but no corresponding label '{basename}.txt'. Skipping.")

if not image_basenames:
    print("Error: No valid image-label pairs found in the source training directories.")
    exit()

total_files = len(image_basenames)
print(f"Found {total_files} image-label pairs for splitting.")

# --- Randomly shuffle the basenames ---
random.shuffle(image_basenames)

# --- Determine number of files to move to validation ---
num_to_move_to_val = max(1, int(total_files * VAL_RATIO)) # Ensure at least 1 file is moved if total > 0
if total_files == 0:
    num_to_move_to_val = 0 # If no files, don't try to move 1

print(f"Will attempt to move {num_to_move_to_val} files to validation set.")

# --- Move files to validation ---
moved_count = 0
for i, basename in enumerate(image_basenames):
    if moved_count >= num_to_move_to_val:
        break # Stop once enough files are moved

    src_png_path = os.path.join(SOURCE_IMAGES_TRAIN_DIR, basename + '.png')
    src_aux_xml_path = os.path.join(SOURCE_IMAGES_TRAIN_DIR, basename + '.png.aux.xml')
    src_txt_path = os.path.join(SOURCE_LABELS_TRAIN_DIR, basename + '.txt')

    dest_png_path = os.path.join(DEST_IMAGES_VAL_DIR, basename + '.png')
    dest_aux_xml_path = os.path.join(DEST_IMAGES_VAL_DIR, basename + '.png.aux.xml')
    dest_txt_path = os.path.join(DEST_LABELS_VAL_DIR, basename + '.txt')

    try:
        # Move PNG image
        shutil.move(src_png_path, dest_png_path)
        
        # Move AUX.XML if it exists
        if os.path.exists(src_aux_xml_path):
            shutil.move(src_aux_xml_path, dest_aux_xml_path)
        else:
            print(f"Info: No .png.aux.xml found for '{basename}.png'.")

        # Move TXT label
        shutil.move(src_txt_path, dest_txt_path)
        
        moved_count += 1
        print(f"Moved '{basename}' to VAL ({moved_count}/{num_to_move_to_val})")

    except FileNotFoundError as e:
        print(f"Error: One or more files for '{basename}' not found during move. Skipping. Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while moving '{basename}': {e}")

remaining_train_count = total_files - moved_count

print("\n--- Split Complete ---")
print(f"Total initial files: {total_files}")
print(f"Files moved to validation: {moved_count}")
print(f"Files remaining in training: {remaining_train_count}")

print("\nPlease verify the contents of:")
print(f"- {SOURCE_IMAGES_TRAIN_DIR} (remaining images)")
print(f"- {SOURCE_LABELS_TRAIN_DIR} (remaining labels)")
print(f"- {DEST_IMAGES_VAL_DIR} (validation images)")
print(f"- {DEST_LABELS_VAL_DIR} (validation labels)")