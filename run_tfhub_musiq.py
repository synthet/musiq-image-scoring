#!/usr/bin/env python3
"""
Script to run MUSIQ using TensorFlow Hub models.
Based on the official MUSIQ TensorFlow Hub implementation.
"""

import os
import sys
import argparse
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
from PIL import Image
import requests
from io import BytesIO

def download_sample_image():
    """Download a sample image if none exists."""
    if not os.path.exists('sample.jpg'):
        print("No sample image found. Downloading a sample image...")
        # Download a sample image from the internet
        url = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Vd-Orig.png/256px-Vd-Orig.png"
        response = requests.get(url)
        if response.status_code == 200:
            with open('sample.jpg', 'wb') as f:
                f.write(response.content)
            print("Sample image downloaded successfully!")
        else:
            print("Failed to download sample image")
            return False
    return True

def preprocess_image(image_path, target_size=(224, 224)):
    """Preprocess image for MUSIQ input."""
    try:
        # Load and preprocess image
        image = Image.open(image_path).convert('RGB')
        image = image.resize(target_size, Image.Resampling.LANCZOS)
        
        # Convert to numpy array and normalize
        image_array = np.array(image, dtype=np.float32) / 255.0
        image_array = np.expand_dims(image_array, axis=0)
        
        return image_array
    except Exception as e:
        print(f"Error preprocessing image: {e}")
        return None

def run_tfhub_musiq(image_path, model_url=None):
    """Run MUSIQ using TensorFlow Hub."""
    
    # Default MUSIQ model URL from TensorFlow Hub
    if model_url is None:
        model_url = "https://tfhub.dev/google/musiq/ava/1"
    
    print(f"Loading MUSIQ model from: {model_url}")
    
    try:
        # Load the model from TensorFlow Hub
        model = hub.load(model_url)
        
        # Preprocess image
        image_array = preprocess_image(image_path)
        if image_array is None:
            return None
        
        print(f"Processing image: {image_path}")
        print(f"Image shape: {image_array.shape}")
        
        # Run inference
        predictions = model(image_array)
        
        # Extract quality score
        if isinstance(predictions, dict):
            quality_score = predictions.get('predictions', predictions.get('output', None))
        else:
            quality_score = predictions
        
        # Convert to scalar if needed
        if hasattr(quality_score, 'numpy'):
            quality_score = float(quality_score.numpy()[0])
        elif isinstance(quality_score, np.ndarray):
            quality_score = float(quality_score[0])
        
        return quality_score
        
    except Exception as e:
        print(f"Error running TensorFlow Hub MUSIQ: {e}")
        return None

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Run MUSIQ using TensorFlow Hub')
    parser.add_argument('--image_path', type=str, default='sample.jpg',
                       help='Path to the input image')
    parser.add_argument('--model_url', type=str, default=None,
                       help='TensorFlow Hub model URL (optional)')
    
    args = parser.parse_args()
    
    # Check if image exists, download if not
    if not os.path.exists(args.image_path):
        if not download_sample_image():
            print("Please provide a valid image file")
            return
    
    print("=" * 60)
    print("Running MUSIQ using TensorFlow Hub...")
    print(f"Image: {args.image_path}")
    print("=" * 60)
    
    # Run MUSIQ
    quality_score = run_tfhub_musiq(args.image_path, args.model_url)
    
    if quality_score is not None:
        print(f"\n🎯 MUSIQ Quality Score: {quality_score:.4f}")
        
        # Provide interpretation
        if quality_score >= 4.0:
            quality_level = "Excellent"
        elif quality_score >= 3.0:
            quality_level = "Good"
        elif quality_score >= 2.0:
            quality_level = "Fair"
        elif quality_score >= 1.0:
            quality_level = "Poor"
        else:
            quality_level = "Very Poor"
            
        print(f"📊 Quality Assessment: {quality_level}")
        print(f"📈 Score Range: 1.0 (worst) to 5.0 (best)")
    else:
        print("❌ Failed to process the image")
    
    print("=" * 60)
    print("MUSIQ analysis complete!")

if __name__ == "__main__":
    main()
