#!/usr/bin/env python3
"""
Run all available MUSIQ models on an image and save results to JSON file.
The JSON file will have the same name as the image but with .json extension.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional
from pathlib import Path

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import kagglehub
from PIL import Image


class MultiModelMUSIQ:
    """Run multiple MUSIQ models on a single image."""
    
    # Version identifier for this implementation
    VERSION = "1.0.0"
    
    def __init__(self):
        self.device = None
        self.gpu_available = False
        self.models = {}
        
        # Available MUSIQ model variants
        # TensorFlow Hub models
        self.tfhub_models = {
            "spaq": "https://tfhub.dev/google/musiq/spaq/1",
            "ava": "https://tfhub.dev/google/musiq/ava/1", 
            "paq2piq": "https://tfhub.dev/google/musiq/paq2piq/1"
        }
        
        # Kaggle Hub models
        self.kaggle_models = {
            "koniq": "google/musiq/tensorFlow2/koniq-10k"
        }
        
        # Combined model sources
        self.model_sources = {
            "spaq": "tfhub",
            "ava": "tfhub", 
            "koniq": "kaggle",
            "paq2piq": "tfhub"
        }
        
        # Model score ranges for reference (from Kaggle documentation)
        self.model_ranges = {
            "spaq": (0.0, 100.0),      # SPAQ dataset: 0-100
            "ava": (1.0, 10.0),        # AVA dataset: 1-10
            "koniq": (0.0, 100.0),     # KONIQ-10k dataset: 0-100
            "paq2piq": (0.0, 100.0)    # PAQ2PIQ dataset: 0-100
        }
        
        # Initialize GPU support
        self._setup_gpu()
    
    def _setup_gpu(self):
        """Setup GPU configuration."""
        gpus = tf.config.experimental.list_physical_devices('GPU')
        if gpus:
            try:
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                self.gpu_available = True
                self.device = '/GPU:0'
                print(f"GPU detected: {len(gpus)} device(s) available")
                print(f"Using device: {self.device}")
            except RuntimeError as e:
                print(f"GPU setup failed: {e}")
                print("Falling back to CPU")
                self.gpu_available = False
                self.device = '/CPU:0'
        else:
            print("No GPU detected, using CPU")
            self.gpu_available = False
            self.device = '/CPU:0'
    
    def load_model(self, model_name: str) -> bool:
        """Load a specific MUSIQ model from TensorFlow Hub or Kaggle Hub."""
        if model_name not in self.model_sources:
            print(f"Error: Unknown model variant '{model_name}'")
            return False
        
        source = self.model_sources[model_name]
        
        try:
            if source == "tfhub":
                url = self.tfhub_models[model_name]
                print(f"Loading {model_name.upper()} model from TensorFlow Hub: {url}")
                with tf.device(self.device):
                    model = hub.load(url)
                    self.models[model_name] = model
                    print(f"{model_name.upper()} model loaded successfully from TensorFlow Hub")
                    return True
                    
            elif source == "kaggle":
                kaggle_path = self.kaggle_models[model_name]
                print(f"Loading {model_name.upper()} model from Kaggle Hub: {kaggle_path}")
                
                # Download model from Kaggle Hub
                model_path = kagglehub.model_download(kaggle_path)
                print(f"Model downloaded to: {model_path}")
                
                # Load the model
                with tf.device(self.device):
                    model = tf.saved_model.load(model_path)
                    self.models[model_name] = model
                    print(f"{model_name.upper()} model loaded successfully from Kaggle Hub")
                    return True
                    
        except Exception as e:
            print(f"Failed to load {model_name.upper()} model: {e}")
            return False
    
    def load_all_models(self) -> Dict[str, bool]:
        """Load all available MUSIQ models."""
        results = {}
        for model_name in self.model_sources.keys():
            results[model_name] = self.load_model(model_name)
        return results
    
    def predict_quality(self, image_path: str, model_name: str) -> Optional[float]:
        """Predict image quality using a specific model."""
        if model_name not in self.models:
            print(f"Error: Model '{model_name}' not loaded")
            return None
        
        model = self.models[model_name]
        
        try:
            # Read image bytes
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            # Ensure tensor is on correct device
            with tf.device(self.device):
                # TensorFlow Hub models expect image bytes as string tensor
                image_bytes_tensor = tf.constant(image_bytes)
                predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
            
            # Extract score
            if isinstance(predictions, dict):
                if 'output_0' in predictions:
                    score = float(predictions['output_0'].numpy().squeeze())
                elif 'predictions' in predictions:
                    score = float(predictions['predictions'].numpy().squeeze())
                elif 'output' in predictions:
                    score = float(predictions['output'].numpy().squeeze())
                else:
                    score = float(list(predictions.values())[0].numpy().squeeze())
            else:
                score = float(predictions.numpy().squeeze())
            
            return score
            
        except Exception as e:
            print(f"Error predicting with {model_name.upper()} model: {e}")
            return None
    
    def run_all_models(self, image_path: str) -> Dict[str, any]:
        """Run all loaded models on the image and return results."""
        results = {
            "version": self.VERSION,
            "image_path": image_path,
            "image_name": os.path.basename(image_path),
            "device": "GPU" if self.gpu_available else "CPU",
            "gpu_available": self.gpu_available,
            "models": {},
            "summary": {
                "total_models": len(self.models),
                "successful_predictions": 0,
                "failed_predictions": 0,
                "average_normalized_score": None
            }
        }
        
        print(f"\nRunning all models on: {image_path}")
        print("=" * 60)
        
        normalized_scores = []
        
        for model_name in self.model_sources.keys():
            if model_name in self.models:
                print(f"Processing with {model_name.upper()} model...")
                score = self.predict_quality(image_path, model_name)
                
                if score is not None:
                    min_score, max_score = self.model_ranges[model_name]
                    normalized_score = (score - min_score) / (max_score - min_score)
                    normalized_scores.append(normalized_score)
                    
                    results["models"][model_name] = {
                        "score": round(score, 2),
                        "score_range": f"{min_score}-{max_score}",
                        "normalized_score": round(normalized_score, 3),
                        "status": "success"
                    }
                    results["summary"]["successful_predictions"] += 1
                    print(f"  {model_name.upper()} score: {score:.2f} (range: {min_score}-{max_score})")
                else:
                    results["models"][model_name] = {
                        "score": None,
                        "error": "Prediction failed",
                        "status": "failed"
                    }
                    results["summary"]["failed_predictions"] += 1
                    print(f"  {model_name.upper()} model: FAILED")
            else:
                results["models"][model_name] = {
                    "score": None,
                    "error": "Model not loaded",
                    "status": "not_loaded"
                }
                results["summary"]["failed_predictions"] += 1
                print(f"  {model_name.upper()} model: NOT LOADED")
        
        # Calculate average normalized score
        if normalized_scores:
            average_normalized = sum(normalized_scores) / len(normalized_scores)
            results["summary"]["average_normalized_score"] = round(average_normalized, 3)
        
        return results
    
    def is_already_processed(self, image_path: str, output_dir: str) -> bool:
        """Check if image has already been processed with current version."""
        image_name = os.path.splitext(os.path.basename(image_path))[0]
        json_path = os.path.join(output_dir, f"{image_name}.json")
        
        if not os.path.exists(json_path):
            return False
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            
            # Check if version matches
            existing_version = existing_data.get('version', 'unknown')
            if existing_version == self.VERSION:
                print(f"Image already processed with version {self.VERSION}: {image_path}")
                return True
            else:
                print(f"Version mismatch - existing: {existing_version}, current: {self.VERSION}")
                return False
                
        except Exception as e:
            print(f"Error checking existing results: {e}")
            return False
    
    def save_results(self, results: Dict[str, any], output_path: str):
        """Save results to JSON file."""
        try:
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {output_path}")
        except Exception as e:
            print(f"Error saving results: {e}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Run all available MUSIQ models on an image and save results to JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_musiq_models.py --image sample.jpg
  python run_all_musiq_models.py --image /path/to/image.jpg --output-dir /path/to/output/
  python run_all_musiq_models.py --image sample.jpg --models spaq ava

Available Models:
  - spaq: SPAQ dataset model (range: 1-5)
  - ava: AVA dataset model (range: 1-10) 
  - koniq: KONIQ-10K dataset model (range: 1-5)
  - paq2piq: PAQ2PIQ dataset model (range: 1-5)
        """
    )
    
    parser.add_argument('--image', required=True, help='Path to input image')
    parser.add_argument('--output-dir', help='Output directory for JSON file (default: same as image directory)')
    parser.add_argument('--models', nargs='+', choices=['spaq', 'ava', 'koniq', 'paq2piq'],
                       help='Specific models to run (default: all models)')
    
    args = parser.parse_args()
    
    # Validate input image
    if not os.path.exists(args.image):
        print(f"Error: Image file not found: {args.image}")
        sys.exit(1)
    
    # Determine output path
    image_path = Path(args.image)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{image_path.stem}.json"
    else:
        output_path = image_path.parent / f"{image_path.stem}.json"
    
    # Initialize multi-model scorer
    scorer = MultiModelMUSIQ()
    
    # Load models
    if args.models:
        # Load specific models
        print(f"Loading specified models: {', '.join(args.models)}")
        for model_name in args.models:
            scorer.load_model(model_name)
    else:
        # Load all models
        print("Loading all available MUSIQ models...")
        load_results = scorer.load_all_models()
        
        # Check if any models loaded successfully
        if not any(load_results.values()):
            print("Error: No models loaded successfully")
            sys.exit(1)
    
    # Check if already processed with current version
    if scorer.is_already_processed(args.image, args.output_dir):
        print(f"Skipping {args.image} - already processed with version {scorer.VERSION}")
        sys.exit(0)
    
    # Run all models on the image
    results = scorer.run_all_models(args.image)
    
    # Save results
    scorer.save_results(results, str(output_path))
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Image: {results['image_name']}")
    print(f"Device: {results['device']}")
    print(f"Models loaded: {results['summary']['total_models']}")
    print(f"Successful predictions: {results['summary']['successful_predictions']}")
    print(f"Failed predictions: {results['summary']['failed_predictions']}")
    
    if results['summary']['average_normalized_score'] is not None:
        print(f"Average normalized score: {results['summary']['average_normalized_score']}")
    
    if results['summary']['successful_predictions'] > 0:
        print("\nScores:")
        for model_name, model_result in results['models'].items():
            if model_result['status'] == 'success':
                print(f"  {model_name.upper()}: {model_result['score']} ({model_result['score_range']}) - Normalized: {model_result['normalized_score']}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
