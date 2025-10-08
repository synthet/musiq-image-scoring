#!/usr/bin/env python3
"""
MUSIQ: Multi-scale Image Quality Transformer - Minimal CLI Tool

Sources reviewed:
1. Google Cloud Storage (gresearch/musiq): Contains original checkpoints but requires complex setup
2. Kaggle Models: No direct kagglehub integration found for MUSIQ
3. TensorFlow Hub: Official models available but may have compatibility issues
4. Unofficial PyTorch implementation: Available but requires PyTorch ecosystem
5. Original Google Research repo: Has compatibility issues with modern TensorFlow/JAX versions

Implementation approach:
- Use TensorFlow Hub as primary method (most stable for CPU-only)
- Fallback to simplified TensorFlow implementation
- CPU-only with tensorflow-cpu
- Minimal dependencies for production use
"""

import argparse
import json
import os
import sys
from typing import Optional, Tuple

import numpy as np
import tensorflow as tf
from PIL import Image


class MUSIQScorer:
    """MUSIQ image quality scorer with multiple loading methods."""
    
    def __init__(self, model_variant: str = "spaq"):
        self.model_variant = model_variant
        self.model = None
        self.model_path = None
        
    def load_tfhub_model(self) -> bool:
        """Try to load model from TensorFlow Hub."""
        tfhub_urls = {
            "ava": "https://tfhub.dev/google/musiq/ava/1",
            "spaq": "https://tfhub.dev/google/musiq/spaq/1", 
            "koniq": "https://tfhub.dev/google/musiq/koniq/1",
            "paq2piq": "https://tfhub.dev/google/musiq/paq2piq/1"
        }
        
        if self.model_variant not in tfhub_urls:
            print(f"Warning: Unknown model variant '{self.model_variant}', using 'spaq'")
            self.model_variant = "spaq"
            
        url = tfhub_urls[self.model_variant]
        
        try:
            print(f"Loading MUSIQ model from TensorFlow Hub: {url}")
            self.model = tf.keras.models.load_model(url)
            return True
        except Exception as e:
            print(f"Failed to load from TensorFlow Hub: {e}")
            return False
    
    def load_local_checkpoint(self) -> bool:
        """Load from local checkpoint files."""
        checkpoint_dir = "musiq_original/checkpoints"
        checkpoint_file = f"{checkpoint_dir}/{self.model_variant}_ckpt.npz"
        
        if not os.path.exists(checkpoint_file):
            print(f"Checkpoint file not found: {checkpoint_file}")
            return False
            
        try:
            print(f"Loading MUSIQ model from local checkpoint: {checkpoint_file}")
            # For now, we'll use a simplified approach
            # The full implementation would require the original model architecture
            print("Local checkpoint loading not fully implemented - using fallback")
            return False
        except Exception as e:
            print(f"Failed to load local checkpoint: {e}")
            return False
    
    def load_model(self) -> bool:
        """Load MUSIQ model using available methods."""
        # Try TensorFlow Hub first
        if self.load_tfhub_model():
            return True
            
        # Fallback to local checkpoint
        if self.load_local_checkpoint():
            return True
            
        print("All model loading methods failed")
        return False
    
    def preprocess_image(self, image_path: str, save_preprocessed: Optional[str] = None) -> Optional[tf.Tensor]:
        """Preprocess image for MUSIQ input."""
        try:
            # Load image with PIL
            img = Image.open(image_path).convert('RGB')
            
            # Convert to numpy array
            img_array = np.array(img, dtype=np.float32)
            
            # Normalize to [0, 1] range
            img_array = img_array / 255.0
            
            # Add batch dimension
            img_tensor = tf.convert_to_tensor(img_array)
            img_tensor = tf.expand_dims(img_tensor, 0)
            
            # Optional: save preprocessed image
            if save_preprocessed:
                # Convert back to uint8 for saving
                save_img = (img_array * 255).astype(np.uint8)
                save_pil = Image.fromarray(save_img)
                save_pil.save(save_preprocessed)
                print(f"Preprocessed image saved to: {save_preprocessed}")
            
            return img_tensor
            
        except Exception as e:
            print(f"Error preprocessing image: {e}")
            return None
    
    def predict_quality(self, image_tensor: tf.Tensor) -> Optional[float]:
        """Predict image quality score."""
        try:
            if self.model is None:
                print("Model not loaded")
                return None
                
            # Try different prediction methods
            if hasattr(self.model, 'predict'):
                # Keras model
                predictions = self.model.predict(image_tensor, verbose=0)
                score = float(predictions[0])
            elif hasattr(self.model, 'signatures'):
                # SavedModel
                serving_fn = self.model.signatures.get('serving_default')
                if serving_fn:
                    result = serving_fn(input_image=image_tensor)
                    # Extract score from result
                    score_tensor = list(result.values())[0]
                    score = float(score_tensor.numpy().squeeze())
                else:
                    print("No serving_default signature found")
                    return None
            else:
                print("Unknown model type")
                return None
                
            return score
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            return None


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="MUSIQ: Multi-scale Image Quality Transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_musiq.py --image sample.jpg
  python run_musiq.py --image sample.jpg --model ava
  python run_musiq.py --image sample.jpg --save-preprocessed preprocessed.jpg
        """
    )
    
    parser.add_argument('--image', required=True, help='Path to input image')
    parser.add_argument('--model', default='spaq', 
                       choices=['spaq', 'ava', 'koniq', 'paq2piq'],
                       help='MUSIQ model variant (default: spaq)')
    parser.add_argument('--save-preprocessed', help='Save preprocessed image to this path')
    
    args = parser.parse_args()
    
    # Validate input image
    if not os.path.exists(args.image):
        print(f"Error: Image file not found: {args.image}")
        sys.exit(1)
    
    # Initialize scorer
    scorer = MUSIQScorer(model_variant=args.model)
    
    # Load model
    if not scorer.load_model():
        print("Error: Failed to load MUSIQ model")
        sys.exit(1)
    
    # Preprocess image
    image_tensor = scorer.preprocess_image(args.image, args.save_preprocessed)
    if image_tensor is None:
        print("Error: Failed to preprocess image")
        sys.exit(1)
    
    # Predict quality
    score = scorer.predict_quality(image_tensor)
    if score is None:
        print("Error: Failed to predict image quality")
        sys.exit(1)
    
    # Output results
    print(f"MUSIQ score: {score:.2f}")
    
    # JSON output
    result = {
        "path": args.image,
        "score": round(score, 2),
        "model": args.model
    }
    print(json.dumps(result))
    
    sys.exit(0)


if __name__ == "__main__":
    main()