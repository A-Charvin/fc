#!/usr/bin/env python3
"""
YOLO Training Script
A clean, organized script for training YOLOv8 models on custom datasets.
"""

import sys
from pathlib import Path
from ultralytics import YOLO


class YOLOTrainer:
    """YOLO model trainer with configuration management and error handling."""
    
    def __init__(self):
        # Training configuration
        self.config = {
            'data_yaml_path': r'C:\GIS_Working\ObjectDetection\DrapePatched\data.yaml',
            'model_weights': 'yolov8s.pt',
            'epochs': 200,
            'image_size': 128,
            'batch_size': 8,
            'run_name': 'road_markings_v2',
            'device': 'cpu'
        }
        
        self.model = None
    
    def validate_config(self):
        """Validate configuration and check file paths."""
        data_path = Path(self.config['data_yaml_path'])
        
        if not data_path.exists():
            print(f"❌ Error: data.yaml not found at '{data_path}'")
            print("Please ensure the data_yaml_path is set correctly.")
            return False
        
        print(f"✅ Using data.yaml from: {data_path}")
        return True
    
    def load_model(self):
        """Load the pre-trained YOLO model."""
        try:
            self.model = YOLO(self.config['model_weights'])
            print(f"✅ Model '{self.config['model_weights']}' loaded successfully.")
            return True
        except Exception as e:
            print(f"❌ Error loading model '{self.config['model_weights']}': {e}")
            print("Please check if the model weights file exists or internet connection for download.")
            return False
    
    def print_training_info(self):
        """Display training configuration information."""
        print("\n" + "="*60)
        print("🚀 YOLO TRAINING CONFIGURATION")
        print("="*60)
        print(f"📁 Data file:     {self.config['data_yaml_path']}")
        print(f"🏗️  Model:        {self.config['model_weights']}")
        print(f"🔄 Epochs:        {self.config['epochs']}")
        print(f"📐 Image size:    {self.config['image_size']}")
        print(f"📦 Batch size:    {self.config['batch_size']}")
        print(f"💻 Device:        {self.config['device']}")
        print(f"📝 Run name:      {self.config['run_name']}")
        print(f"💾 Output dir:    runs/detect/{self.config['run_name']}")
        print("="*60)
    
    def train(self):
        """Execute the training process."""
        print(f"\n🏃 Starting training on {self.config['device'].upper()}...")
        print("⏳ This may take a considerable amount of time...\n")
        
        try:
            results = self.model.train(  # type: ignore
                data=self.config['data_yaml_path'],
                epochs=self.config['epochs'],
                imgsz=self.config['image_size'],
                batch=self.config['batch_size'],
                name=self.config['run_name'],
                device=self.config['device']
            )
            
            print("\n🎉 Training completed successfully!")
            return results
            
        except Exception as e:
            print(f"\n❌ Training failed: {e}")
            print("💡 Common issues:")
            print("   • Insufficient RAM (try reducing batch size)")
            print("   • Incorrect data.yaml configuration")
            print("   • Corrupted or missing training data")
            return None
    
    def print_results_info(self):
        """Display information about training results."""
        results_path = Path.cwd() / 'runs' / 'detect' / self.config['run_name']
        
        print("\n" + "="*60)
        print("📊 TRAINING RESULTS")
        print("="*60)
        print(f"📂 Results location: {results_path}")
        print("📋 Key files to check:")
        print("   • results.png     - Training metrics plots")
        print("   • weights/best.pt - Best performing model")
        print("   • weights/last.pt - Final epoch model")
        print("   • confusion_matrix.png - Model performance matrix")
        print("="*60)
    
    def run(self):
        """Execute the complete training workflow."""
        print("🔍 Validating configuration...")
        if not self.validate_config():
            sys.exit(1)
        
        print("📥 Loading model...")
        if not self.load_model():
            sys.exit(1)
        
        self.print_training_info()
        
        # Confirm before starting training
        response = input("\n❓ Start training? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Training cancelled.")
            return
        
        results = self.train()
        
        if results is not None:
            self.print_results_info()
        else:
            print("\n💥 Training was unsuccessful. Please check the errors above.")
            sys.exit(1)


def main():
    """Main entry point."""
    trainer = YOLOTrainer()
    trainer.run()


if __name__ == "__main__":
    main()