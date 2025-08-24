"""
YOLOv8 Training Script
Optimized, compact script for training YOLOv8 models.
"""
import sys
import warnings
import os
import logging
from pathlib import Path
from dataclasses import dataclass
from ultralytics import YOLO
import torch

# Aggressive warning suppression
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'

# Disable all logging below ERROR level
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('ultralytics').setLevel(logging.ERROR)

# Suppress all warnings
warnings.filterwarnings('ignore')
warnings.simplefilter('ignore')

# Redirect stderr to null to catch C library warnings
import subprocess
import tempfile

def suppress_stderr():
    """Redirect stderr to suppress C library warnings."""
    devnull = open(os.devnull, 'w')
    old_stderr = os.dup(2)
    os.dup2(devnull.fileno(), 2)
    return old_stderr, devnull

def restore_stderr(old_stderr, devnull):
    """Restore stderr."""
    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    devnull.close()


@dataclass
class Config:
    """Training configuration optimized for patch-based datasets."""
    data_yaml_path: str = r'I:\Drape\DrapeYOLO_Patches2\data.yaml' # Data.yml location - This will be inside your Training data folder.
    # This is what the content of the data.yaml looks like. 
        '''' 
        # data.yaml
        path: I:/Drape/DrapeYOLO_Patches2 # This is the root where out 'images' and 'labels' folders are for the patches
        train: images/train              # Path to training images relative to 'path'
        val: images/val                  # Path to validation images relative to 'path'
        nc: 6                            # Number of classes (should be the same as the original classes)
        names: ['StopBar', 'TurnArrow', 'CrossWalk', 'Diamond', 'CycleLane', 'Cross'] # The class names 
        '''
    
    model_weights: str = 'yolov8s.pt'
    epochs: int = 300  # More epochs for patch dataset
    image_size: int = 128  # Match patch size
    batch_size: int = 16  # Larger batch for small patches
    run_name: str = 'road_markings_patches_v1'
    device: str = None
    patience: int = 150
    
    def __post_init__(self):
        # Auto-detect device and optimize for patch training
        if self.device is None:
            if torch.cuda.is_available():
                self.device = 'cuda'
                # Patches are small, can use larger batch size
                gpu_memory = torch.cuda.get_device_properties(0).total_memory
                if gpu_memory < 8e9:  # <8GB
                    self.batch_size = min(self.batch_size, 8)
                else:  # >=8GB
                    self.batch_size = min(self.batch_size, 32)
            else:
                self.device = 'cpu'
                self.batch_size = min(self.batch_size, 4)
        
        # Patches are already 128x128, no need to adjust
        print(f"🔧 Optimized for patch training: {self.image_size}px patches, batch={self.batch_size}")


class YOLOTrainer:
    """Compact YOLO trainer."""
    
    def __init__(self, config=None):
        self.config = config or Config()
        self.model = None
    
    def validate_data(self):
        """Check if data.yaml exists."""
        data_path = Path(self.config.data_yaml_path)
        if not data_path.exists():
            print(f"❌ Data file not found: {data_path}")
            return False
        print(f"✅ Data file found: {data_path}")
        return True
    
    def load_model(self):
        """Load YOLO model."""
        try:
            self.model = YOLO(self.config.model_weights)
            print(f"✅ Model loaded: {self.config.model_weights}")
            return True
        except Exception as e:
            print(f"❌ Model loading failed: {e}")
            return False
    
    def print_config(self):
        """Display training configuration."""
        print("\n" + "="*50)
        print("🚀 YOLO TRAINING CONFIG")
        print("="*50)
        print(f"📁 Data:      {self.config.data_yaml_path}")
        print(f"🏗️  Model:     {self.config.model_weights}")
        print(f"🔄 Epochs:    {self.config.epochs}")
        print(f"📐 Size:      {self.config.image_size}")
        print(f"📦 Batch:     {self.config.batch_size}")
        print(f"💻 Device:    {self.config.device}")
        print(f"📝 Name:      {self.config.run_name}")
        print("="*50)
    
    def train(self):
        """Execute training optimized for patch dataset."""
        print(f"\n🏃 Starting patch-based training on {self.config.device.upper()}...")
        print("📦 Training with sliding window patches (libpng warnings suppressed)")
        
        try:
            results = self.model.train(
                data=self.config.data_yaml_path,
                epochs=self.config.epochs,
                imgsz=self.config.image_size,
                batch=self.config.batch_size,
                name=self.config.run_name,
                device=self.config.device,
                patience=self.config.patience,
                verbose=True,
                plots=True,
                save_period=25,  # Save less frequently for patch training
                amp=True,  # Mixed precision
                cos_lr=True,  # Cosine LR scheduler
                # Patch-specific optimizations
                mosaic=0.5,  # Reduce mosaic for small patches
                mixup=0.0,   # Disable mixup for patches
                copy_paste=0.0,  # Disable copy-paste
                degrees=5.0,     # Small rotation for patches
                translate=0.1,   # Small translation
                scale=0.2,       # Small scale variation
                fliplr=0.5,      # Horizontal flip OK
                flipud=0.0,      # No vertical flip for road markings
                hsv_h=0.015,     # Small hue variation
                hsv_s=0.7,       # Saturation variation
                hsv_v=0.4,       # Brightness variation
            )
            
            print("\n🎉 Patch training completed successfully!")
            return results
            
        except KeyboardInterrupt:
            print("⏹️  Training interrupted")
            return None
        except torch.cuda.OutOfMemoryError:
            print("💥 GPU out of memory! Try reducing batch_size")
            print("💡 For patch training, try batch_size: 16→8→4")
            return None
        except Exception as e:
            print(f"❌ Training failed: {e}")
            print("💡 Patch training tips: check data.yaml points to patch dataset")
            return None
    
    def print_results(self):
        """Show results location."""
        results_path = Path.cwd() / 'runs' / 'detect' / self.config.run_name
        print(f"\n📊 Results saved to: {results_path}")
        print("📋 Key files:")
        print("   • results.png - Training metrics")
        print("   • weights/best.pt - Best model")
        print("   • confusion_matrix.png - Performance matrix")
    
    def run(self):
        """Main training workflow."""
        # Validate
        if not self.validate_data():
            sys.exit(1)
        
        # Load model
        if not self.load_model():
            sys.exit(1)
        
        # Show config
        self.print_config()
        
        # Confirm
        response = input("\n❓ Start training? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Training cancelled")
            return
        
        # Train
        results = self.train()
        
        # Results
        if results is not None:
            self.print_results()
        else:
            sys.exit(1)


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', help='Path to data.yaml')
    parser.add_argument('--model', default='yolov8s.pt', help='Model weights')
    parser.add_argument('--epochs', type=int, default=200, help='Training epochs')
    parser.add_argument('--batch', type=int, default=8, help='Batch size')
    parser.add_argument('--imgsz', type=int, default=128, help='Image size')
    parser.add_argument('--name', default='road_markings_v2', help='Run name')
    parser.add_argument('--device', help='Training device')
    
    args = parser.parse_args()
    
    # Create config
    config = Config()
    if args.data:
        config.data_yaml_path = args.data
    config.model_weights = args.model
    config.epochs = args.epochs
    config.batch_size = args.batch
    config.image_size = args.imgsz
    config.run_name = args.name
    if args.device:
        config.device = args.device
    
    # Run trainer
    trainer = YOLOTrainer(config)
    trainer.run()


if __name__ == "__main__":
    main()
