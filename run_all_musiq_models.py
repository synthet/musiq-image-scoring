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
    """Run multiple MUSIQ and VILA models on a single image."""
    
    # Version identifier for this implementation
    VERSION = "2.3.0"  # Triple fallback: TFHub → Kaggle Hub → Local Checkpoints
    
    def __init__(self):
        self.device = None
        self.gpu_available = False
        self.models = {}
        
        # Model availability on different platforms
        # All models with TensorFlow Hub, Kaggle Hub, and local checkpoint paths
        # Format: {"model": {"tfhub": "url", "kaggle": "path", "local": "checkpoint_file"}}
        # Fallback order: TF Hub → Kaggle Hub → Local Checkpoints
        
        # Get base directory for local checkpoints
        base_dir = os.path.dirname(os.path.abspath(__file__))
        checkpoint_dir = os.path.join(base_dir, "musiq_original", "checkpoints")
        
        self.model_sources = {
            "spaq": {
                "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
                "kaggle": "google/musiq/tensorFlow2/spaq",
                "local": os.path.join(checkpoint_dir, "spaq_ckpt.npz")
            },
            "ava": {
                "tfhub": "https://tfhub.dev/google/musiq/ava/1",
                "kaggle": "google/musiq/tensorFlow2/ava",
                "local": os.path.join(checkpoint_dir, "ava_ckpt.npz")
            },
            "koniq": {
                "tfhub": None,  # Not available on TF Hub
                "kaggle": "google/musiq/tensorFlow2/koniq-10k",
                "local": os.path.join(checkpoint_dir, "koniq_ckpt.npz")
            },
            "paq2piq": {
                "tfhub": "https://tfhub.dev/google/musiq/paq2piq/1",
                "kaggle": "google/musiq/tensorFlow2/paq2piq",
                "local": os.path.join(checkpoint_dir, "paq2piq_ckpt.npz")
            },
            "vila": {
                "tfhub": "https://tfhub.dev/google/vila/image/1",
                "kaggle": "google/vila/tensorFlow2/image",
                "local": os.path.join(checkpoint_dir, "vila-tensorflow2-image-v1")  # SavedModel format
            }
        }
        
        # Model types (for processing logic)
        self.model_types = {
            "spaq": "musiq",
            "ava": "musiq",
            "koniq": "musiq",
            "paq2piq": "musiq",
            "vila": "vila"
        }
        
        # Model score ranges for reference (from official documentation)
        self.model_ranges = {
            "spaq": (0.0, 100.0),      # SPAQ dataset: 0-100
            "ava": (1.0, 10.0),        # AVA dataset: 1-10
            "koniq": (0.0, 100.0),     # KONIQ-10k dataset: 0-100
            "paq2piq": (0.0, 100.0),   # PAQ2PIQ dataset: 0-100
            "vila": (0.0, 1.0)         # VILA aesthetic score: 0-1 (official range)
        }
        
        # Initialize GPU support
        self._setup_gpu()
        
        # Model weights for weighted scoring (based on statistical analysis)
        self.model_weights = {
            "koniq": 0.30,      # Best balance of discrimination and reliability
            "spaq": 0.25,       # Best discrimination (widest range)
            "paq2piq": 0.20,    # Most lenient, good for high-quality detection
            "vila": 0.15,       # Vision-language aesthetics assessment
            "ava": 0.10         # Most conservative, narrow range
        }
    
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
        """
        Load a model with triple fallback mechanism:
        1. TensorFlow Hub (fast, no auth) 
        2. Kaggle Hub (requires auth)
        3. Local checkpoints (offline fallback)
        
        This provides maximum reliability across different network conditions,
        authentication states, and offline scenarios.
        """
        if model_name not in self.model_sources:
            print(f"Error: Unknown model variant '{model_name}'")
            return False
        
        sources = self.model_sources[model_name]
        tfhub_url = sources.get("tfhub")
        kaggle_path = sources.get("kaggle")
        local_path = sources.get("local")
        
        # Try TensorFlow Hub first (preferred - no auth needed, usually faster)
        if tfhub_url:
            try:
                print(f"Loading {model_name.upper()} model from TensorFlow Hub: {tfhub_url}")
                with tf.device(self.device):
                    model = hub.load(tfhub_url)
                    self.models[model_name] = model
                    print(f"✓ {model_name.upper()} model loaded successfully from TensorFlow Hub")
                    return True
            except Exception as e:
                print(f"⚠ TensorFlow Hub failed for {model_name.upper()}: {str(e)[:80]}...")
                print(f"  Falling back to Kaggle Hub...")
        
        # Fall back to Kaggle Hub (requires authentication)
        if kaggle_path:
            try:
                print(f"Loading {model_name.upper()} model from Kaggle Hub: {kaggle_path}")
                
                # Download model from Kaggle Hub
                model_path = kagglehub.model_download(kaggle_path)
                print(f"Model downloaded to: {model_path}")
                
                # Load the model
                with tf.device(self.device):
                    model = tf.saved_model.load(model_path)
                    self.models[model_name] = model
                    print(f"✓ {model_name.upper()} model loaded successfully from Kaggle Hub")
                    return True
                    
            except Exception as e:
                print(f"⚠ Kaggle Hub failed for {model_name.upper()}: {str(e)[:80]}...")
                print(f"  Falling back to local checkpoint...")
        
        # Fall back to local checkpoint (offline, no network needed)
        if local_path and os.path.exists(local_path):
            try:
                print(f"Loading {model_name.upper()} model from local checkpoint: {local_path}")
                
                with tf.device(self.device):
                    # Check if it's a SavedModel directory or .npz file
                    if os.path.isdir(local_path):
                        # Load SavedModel (VILA cached model)
                        model = tf.saved_model.load(local_path)
                        self.models[model_name] = model
                        print(f"✓ {model_name.upper()} model loaded successfully from local SavedModel")
                        return True
                    elif local_path.endswith('.npz'):
                        # Load .npz checkpoint (MUSIQ models)
                        # Note: .npz files require the original MUSIQ loading code
                        # For now, try loading as SavedModel if conversion exists
                        print(f"⚠ .npz checkpoint loading not yet implemented for {model_name.upper()}")
                        print(f"  Checkpoint available at: {local_path}")
                        print(f"  Consider using TF Hub or Kaggle Hub sources instead")
                        return False
                    else:
                        print(f"⚠ Unknown local checkpoint format: {local_path}")
                        return False
                        
            except Exception as e:
                print(f"✗ Failed to load {model_name.upper()} model from local checkpoint: {str(e)[:80]}...")
        elif local_path:
            print(f"⚠ Local checkpoint not found: {local_path}")
            print(f"  Download checkpoints from: https://storage.googleapis.com/gresearch/musiq/")
        
        # All sources failed or unavailable
        print(f"✗ Failed to load {model_name.upper()} model: All available sources failed")
        if "vila" in model_name.lower():
            print("\nNote: For VILA model:")
            print("  - TF Hub: No authentication needed")
            print("  - Kaggle Hub: Requires kaggle.json authentication")
            print("  See docs/vila/README_VILA.md for setup instructions.")
        else:
            print("\nNote: For MUSIQ models:")
            print("  - TF Hub: No authentication needed (recommended)")
            print("  - Kaggle Hub: Requires kaggle.json authentication")
            print("  - Local .npz: Download from https://storage.googleapis.com/gresearch/musiq/")
        
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
        model_type = self.model_types.get(model_name, "musiq")
        
        try:
            # Read image bytes
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            # Ensure tensor is on correct device
            with tf.device(self.device):
                # TensorFlow Hub/Kaggle models expect image bytes as string tensor
                image_bytes_tensor = tf.constant(image_bytes)
                
                # Determine correct parameter name for model
                # VILA models use 'image_bytes', MUSIQ models use 'image_bytes_tensor'
                if model_type == "vila":
                    predictions = model.signatures['serving_default'](image_bytes=image_bytes_tensor)
                else:
                    predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
            
            # Extract score based on model type
            if model_type == "vila":
                # VILA models may have different output structure
                if isinstance(predictions, dict):
                    # Try common output names for aesthetic scores
                    if 'aesthetic_score' in predictions:
                        score = float(predictions['aesthetic_score'].numpy().squeeze())
                    elif 'score' in predictions:
                        score = float(predictions['score'].numpy().squeeze())
                    elif 'output_0' in predictions:
                        score = float(predictions['output_0'].numpy().squeeze())
                    else:
                        # Use first numeric output
                        score = float(list(predictions.values())[0].numpy().squeeze())
                else:
                    score = float(predictions.numpy().squeeze())
            else:
                # MUSIQ models
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
            
            # Calculate advanced scoring methods
            normalized_scores_dict = {}
            for model_name, model_result in results["models"].items():
                if model_result["status"] == "success":
                    normalized_scores_dict[model_name] = model_result["normalized_score"]
            
            if normalized_scores_dict:
                advanced_scores = self.calculate_advanced_scores(normalized_scores_dict)
                results["summary"]["advanced_scoring"] = advanced_scores
        
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
    
    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted average score."""
        weighted_sum = 0.0
        total_weight = 0.0
        
        for model, score in scores.items():
            if model in self.model_weights:
                weight = self.model_weights[model]
                weighted_sum += score * weight
                total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def calculate_median_score(self, scores: Dict[str, float]) -> float:
        """Calculate median score (robust to outliers)."""
        valid_scores = [score for score in scores.values() if score is not None]
        return np.median(valid_scores) if valid_scores else 0.0
    
    def calculate_trimmed_mean(self, scores: Dict[str, float], trim_percent: float = 0.1) -> float:
        """Calculate trimmed mean (remove extreme values)."""
        valid_scores = [score for score in scores.values() if score is not None]
        if not valid_scores:
            return 0.0
        
        valid_scores.sort()
        n = len(valid_scores)
        trim_count = int(n * trim_percent)
        
        if trim_count > 0:
            trimmed_scores = valid_scores[trim_count:-trim_count]
        else:
            trimmed_scores = valid_scores
        
        return np.mean(trimmed_scores) if trimmed_scores else 0.0
    
    def detect_outliers(self, scores: Dict[str, float]) -> List[str]:
        """Detect models with outlier scores using IQR method."""
        valid_scores = [(model, score) for model, score in scores.items() if score is not None]
        if len(valid_scores) < 3:
            return []
        
        scores_only = [score for _, score in valid_scores]
        q1 = np.percentile(scores_only, 25)
        q3 = np.percentile(scores_only, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        outliers = []
        for model, score in valid_scores:
            if score < lower_bound or score > upper_bound:
                outliers.append(model)
        
        return outliers
    
    def calculate_advanced_scores(self, normalized_scores: Dict[str, float]) -> Dict[str, float]:
        """Calculate advanced scoring methods."""
        # Remove outliers
        outliers = self.detect_outliers(normalized_scores)
        filtered_scores = {k: v for k, v in normalized_scores.items() if k not in outliers}
        
        # Calculate different scoring methods
        weighted = self.calculate_weighted_score(filtered_scores)
        median = self.calculate_median_score(filtered_scores)
        trimmed_mean = self.calculate_trimmed_mean(filtered_scores)
        
        # Combine methods (weighted average of methods)
        final_score = (weighted * 0.5 + median * 0.3 + trimmed_mean * 0.2)
        
        return {
            "weighted_score": round(weighted, 3),
            "median_score": round(median, 3),
            "trimmed_mean_score": round(trimmed_mean, 3),
            "final_robust_score": round(final_score, 3),
            "outliers_detected": outliers,
            "outlier_count": len(outliers),
            "models_used": len(filtered_scores)
        }
    
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
  python run_all_musiq_models.py --image sample.jpg --models spaq ava vila

Available Models:
  MUSIQ Models (Image Quality):
  - spaq: SPAQ dataset model (range: 0-100)
  - ava: AVA dataset model (range: 1-10) 
  - koniq: KONIQ-10K dataset model (range: 0-100)
  - paq2piq: PAQ2PIQ dataset model (range: 0-100)
  
  VILA Model (Vision-Language Aesthetics):
  - vila: VILA aesthetic assessment (range: 0-1)
        """
    )
    
    parser.add_argument('--image', required=True, help='Path to input image')
    parser.add_argument('--output-dir', help='Output directory for JSON file (default: same as image directory)')
    parser.add_argument('--models', nargs='+', 
                       choices=['spaq', 'ava', 'koniq', 'paq2piq', 'vila'],
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
    
    # Show advanced scoring if available
    if 'advanced_scoring' in results['summary']:
        advanced = results['summary']['advanced_scoring']
        print(f"Weighted score: {advanced['weighted_score']}")
        print(f"Median score: {advanced['median_score']}")
        print(f"Final robust score: {advanced['final_robust_score']}")
        if advanced['outlier_count'] > 0:
            print(f"Outliers detected: {advanced['outliers_detected']}")
    
    if results['summary']['successful_predictions'] > 0:
        print("\nScores:")
        for model_name, model_result in results['models'].items():
            if model_result['status'] == 'success':
                print(f"  {model_name.upper()}: {model_result['score']} ({model_result['score_range']}) - Normalized: {model_result['normalized_score']}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
