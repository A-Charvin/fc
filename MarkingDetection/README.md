# Road Marking Extraction & Detection

A lightweight, open-data–friendly pipeline for detecting road markings from aerial imagery using **YOLOv8**.
This workflow covers everything from **data preparation**, to **model training**, to **running detections and exporting results** in usable geospatial formats.

---

## 📖 Project Story

This project started not as a planned machine learning workflow, but as a “hey, what if we tried this?” moment.
We don’t currently have dedicated ML infrastructure — no big GPUs, no cloud training clusters — just freely available tools, our existing Python/GIS stack, and a willingness to experiment.

The main goal was simple:

> **Detect only the objects on the road**, without wasting resources on irrelevant areas.

We approached this by:

* Buffering road centerlines by 5 m to create a mask for detection and filtering
* Cropping aerial images into smaller tiles so the model could focus on relevant features
* Avoiding huge, slow training sets by turning each labeled object into its own training patch

Along the way, we:

* Found the **best model performance at epoch 194** (even though training ran for 300 epochs)
* Optimized processing to save time without losing accuracy
* Learned that sometimes “thrown together” experiments can yield production-ready workflows

Special thanks to our team at FrontenacGIS for making this possible.

---

## 📂 Repository Structure

```
.
├── DataPreparation/
│   ├── PatchGeneration.py
│   ├── Split.py
│
├── Training/
│   ├── TrainModel.py
│
├── Detection/
│   ├── Detect2GeoJ.py
│   ├── Detect2Img.py
│   ├── Model/
│       ├── V1/
│       │   ├── best.pt
│       ├── V2/
│           ├── best.pt
```

---

## 1️⃣ Data Preparation

**Folder:** `DataPreparation/`

* **PatchGeneration.py**
  Generates **128×128 image patches** from original aerial imagery and corresponding labels.
  For each labeled object, the script locates it in the original image and crops out a centered patch for use in training.
  This focuses the model’s learning on relevant features and improves efficiency.

* **Split.py**
  Randomly splits patched images into **training** (80%) and **validation** (20%) sets.
  Ensures a reproducible dataset structure for YOLO training.

---

## 2️⃣ Training

**Folder:** `Training/`

* **TrainModel.py**

  ```
  YOLO Training Script
  A clean, organized script for training YOLOv8 models on custom datasets.
  ```

  Trains YOLOv8 models using the prepared dataset.
  Adjustable parameters include epochs, batch size, image size, and more.
  Designed to work with datasets generated from the `DataPreparation` stage.

---

## 3️⃣ Detection

**Folder:** `Detection/`

* **Detect2GeoJ.py**
  Runs object detection on input images and **exports results as a GeoJSON** containing detection coordinates and labels.
  Ideal for GIS integration.

* **Detect2Img.py**
  Runs detection and outputs a **visualized image** with detection markings for quick verification of model performance.

**Model Folder:**
Contains trained YOLOv8 model weights from previous runs:

* `V1/best.pt` — initial trained model
* `V2/best.pt` — improved/optimized trained model

---

## 🚀 How It Works

1. **Prepare Data**

   * Generate object-centered patches with `PatchGeneration.py`
   * Split into training/validation sets with `Split.py`

2. **Train Model**

   * Train YOLOv8 using `TrainModel.py` with your prepared dataset

3. **Run Detection**

   * For GIS-ready output: run `Detect2GeoJ.py`
   * For visual output: run `Detect2Img.py`

---

## 🛠 Requirements

* Python 3.10+
* [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
* Pillow
* numpy
* pyproj
* rasterio
* geopandas
* sahi
* matplotlib

Install them all via:

`pip install -r requirements.txt`

---

## 📌 Notes

* Designed for **publicly available aerial imagery** workflows
* Built to be modular and adaptable for other object detection use cases
* Production models are included in `Detection/Model/` for quick testing
