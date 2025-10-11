#!/usr/bin/env python3
"""
VILA: Vision-Language model for Image Aesthetic Assessment
Google's VILA model from Kaggle Hub
"""

import argparse
import json
import os
import sys
from typing import Optional

import numpy as np
import tensorflow as tf
import kagglehub
from PIL import Image


class VILAScorer:
    """VILA image aesthetic scorer with Kaggle Hub integration."""
    
    def __init__(self, model_variant: str = "vila"):
        self.model_variant = model_variant
        self.model = None
        self.model_path = None
        
        # VILA model on Kaggle Hub
        self.kaggle_models = {
            "vila": "google/vila/tensorFlow2/image"
        }
        
    def load_model(self) -> bool:
        """Load VILA model from Kaggle Hub."""
        if self.model_variant not in self.kaggle_models:
            print(f"Warning: Unknown model variant '{self.model_variant}', using 'vila'")
            self.model_variant = "vila"
        
        kaggle_path = self.kaggle_models[self.model_variant]
        
        try:
            print(f"Loading VILA model from Kaggle Hub: {kaggle_path}")
            
            # Download model from Kaggle Hub
            self.model_path = kagglehub.model_download(kaggle_path)
            print(f"Model downloaded to: {self.model_path}")
            
            # Load the TensorFlow SavedModel
            self.model = tf.saved_model.load(self.model_path)
            print(f"VILA model loaded successfully")
            return True
            
        except Exception as e:
            print(f"Failed to load VILA model: {e}")
            print("\nNote: VILA model requires:")
            print("  1. kagglehub package: pip install kagglehub")
            print("  2. Kaggle authentication (kaggle.json in ~/.kaggle/ or %USERPROFILE%/.kaggle/)")
            print("\nTo set up Kaggle authentication:")
            print("  1. Create a Kaggle account at https://www.kaggle.com")
            print("  2. Go to Account Settings -> API -> Create New API Token")
            print("  3. Place kaggle.json in the appropriate directory")
            return False
    
    def preprocess_image(self, image_path: str) -> Optional[bytes]:
        """Preprocess image for VILA input."""
        try:
            # Read image bytes directly
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            return image_bytes
            
        except Exception as e:
            print(f"Error preprocessing image: {e}")
            return None
    
    def predict_aesthetics(self, image_bytes: bytes) -> Optional[dict]:
        """Predict image aesthetics using VILA model."""
        try:
            if self.model is None:
                print("Model not loaded")
                return None
            
            # Convert image bytes to tensor
            image_bytes_tensor = tf.constant(image_bytes)
            
            # Get model signature
            serving_fn = self.model.signatures.get('serving_default')
            if not serving_fn:
                print("No serving_default signature found in model")
                return None
            
            # Run inference
            result = serving_fn(image_bytes=image_bytes_tensor)
            
            # Extract results
            # VILA models typically output aesthetic score and possibly caption/features
            output_dict = {}
            
            for key, value in result.items():
                try:
                    numpy_value = value.numpy()
                    
                    # Handle different output types
                    if numpy_value.shape == () or len(numpy_value.shape) == 0:
                        # Scalar value
                        output_dict[key] = float(numpy_value)
                    elif len(numpy_value.shape) == 1 and numpy_value.shape[0] == 1:
                        # Single value in array
                        output_dict[key] = float(numpy_value[0])
                    elif len(numpy_value.shape) == 2 and numpy_value.shape[0] == 1:
                        # Batch dimension with single item
                        output_dict[key] = float(numpy_value[0][0])
                    else:
                        # Keep as array for features/embeddings
                        output_dict[key] = numpy_value.tolist()
                        
                except Exception as e:
                    print(f"Warning: Could not process output {key}: {e}")
            
            return output_dict
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            return None


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="VILA: Vision-Language Image Aesthetic Assessment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_vila.py --image sample.jpg

Available Models:
  - vila: VILA model for image aesthetic assessment
        """
    )
    
    parser.add_argument('--image', required=True, help='Path to input image')
    parser.add_argument('--model', default='vila', 
                       choices=['vila'],
                       help='VILA model variant (default: vila)')
    
    args = parser.parse_args()
    
    # Validate input image
    if not os.path.exists(args.image):
        print(f"Error: Image file not found: {args.image}")
        sys.exit(1)
    
    # Initialize scorer
    scorer = VILAScorer(model_variant=args.model)
    
    # Load model
    if not scorer.load_model():
        print("Error: Failed to load VILA model")
        sys.exit(1)
    
    # Preprocess image
    image_bytes = scorer.preprocess_image(args.image)
    if image_bytes is None:
        print("Error: Failed to preprocess image")
        sys.exit(1)
    
    # Predict aesthetics
    results = scorer.predict_aesthetics(image_bytes)
    if results is None:
        print("Error: Failed to predict image aesthetics")
        sys.exit(1)
    
    # Output results
    print(f"\nVILA Model: {args.model}")
    print("=" * 60)
    
    # Try to find the main aesthetic score
    score = None
    if 'output_0' in results:
        score = results['output_0']
    elif 'score' in results:
        score = results['score']
    elif 'aesthetic_score' in results:
        score = results['aesthetic_score']
    else:
        # Use first numeric output
        for key, value in results.items():
            if isinstance(value, (int, float)):
                score = value
                break
    
    if score is not None:
        print(f"Aesthetic Score: {score:.3f}")
    
    # Print all outputs
    print("\nAll Model Outputs:")
    for key, value in results.items():
        if isinstance(value, (int, float)):
            print(f"  {key}: {value:.3f}")
        elif isinstance(value, list) and len(value) < 10:
            print(f"  {key}: {value}")
        else:
            print(f"  {key}: <array/embedding>")
    
    # JSON output
    result_dict = {
        "path": args.image,
        "model": args.model,
        "score": round(score, 3) if score is not None else None,
        "outputs": {k: v for k, v in results.items() if isinstance(v, (int, float))}
    }
    print(f"\nJSON: {json.dumps(result_dict)}")
    
    sys.exit(0)


if __name__ == "__main__":
    main()

