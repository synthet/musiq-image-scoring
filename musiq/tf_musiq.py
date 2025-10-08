"""
Simplified MUSIQ (Multi-Scale Image Quality Transformer) Implementation using TensorFlow
Based on the paper: "MUSIQ: Multi-Scale Image Quality Transformer"
This is a simplified version for demonstration purposes.
"""

import numpy as np
import tensorflow as tf
from PIL import Image
import argparse
import os
from typing import Tuple, Optional


class MultiScalePatchEmbedding(tf.keras.layers.Layer):
    """Multi-scale patch embedding layer."""
    
    def __init__(self, patch_size=16, embed_dim=768, **kwargs):
        super().__init__(**kwargs)
        self.patch_size = patch_size
        self.embed_dim = embed_dim
        self.projection = tf.keras.layers.Conv2D(
            filters=embed_dim,
            kernel_size=patch_size,
            strides=patch_size,
            name='patch_projection'
        )
        
    def call(self, x):
        # Convert image to patches
        patches = self.projection(x)
        batch_size, height, width, channels = tf.unstack(tf.shape(patches))
        patches = tf.reshape(patches, [batch_size, height * width, channels])
        return patches


class MUSIQTransformer(tf.keras.Model):
    """Simplified MUSIQ Transformer model using TensorFlow."""
    
    def __init__(self, num_layers=6, num_heads=12, embed_dim=768, ff_dim=3072, **kwargs):
        super().__init__(**kwargs)
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.embed_dim = embed_dim
        self.ff_dim = ff_dim
        
        # Patch embedding
        self.patch_embedding = MultiScalePatchEmbedding(embed_dim=embed_dim)
        
        # Positional encoding
        self.pos_embedding = tf.keras.layers.Embedding(1000, embed_dim)
        
        # Transformer layers
        self.transformer_layers = []
        for i in range(num_layers):
            layer = {
                'norm1': tf.keras.layers.LayerNormalization(epsilon=1e-6),
                'attention': tf.keras.layers.MultiHeadAttention(
                    num_heads=num_heads,
                    key_dim=embed_dim // num_heads,
                    dropout=0.1
                ),
                'norm2': tf.keras.layers.LayerNormalization(epsilon=1e-6),
                'ffn': tf.keras.Sequential([
                    tf.keras.layers.Dense(ff_dim, activation='gelu'),
                    tf.keras.layers.Dropout(0.1),
                    tf.keras.layers.Dense(embed_dim),
                    tf.keras.layers.Dropout(0.1)
                ])
            }
            self.transformer_layers.append(layer)
        
        # Output head
        self.norm_out = tf.keras.layers.LayerNormalization(epsilon=1e-6)
        self.global_pool = tf.keras.layers.GlobalAveragePooling1D()
        self.quality_head = tf.keras.Sequential([
            tf.keras.layers.Dense(512, activation='gelu'),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(1, activation='sigmoid')  # Quality score between 0 and 1
        ])
        
    def call(self, x, training=False):
        batch_size = tf.shape(x)[0]
        
        # Patch embedding
        patches = self.patch_embedding(x)
        seq_len = tf.shape(patches)[1]
        
        # Positional encoding
        positions = tf.range(seq_len)
        pos_embeds = self.pos_embedding(positions)
        x = patches + pos_embeds
        
        # Transformer layers
        for layer in self.transformer_layers:
            # Self-attention
            norm_x = layer['norm1'](x)
            attn_out = layer['attention'](norm_x, norm_x, training=training)
            x = x + attn_out
            
            # Feed-forward
            norm_x = layer['norm2'](x)
            ffn_out = layer['ffn'](norm_x, training=training)
            x = x + ffn_out
        
        # Output
        x = self.norm_out(x)
        x = self.global_pool(x)
        quality_score = self.quality_head(x, training=training)
        
        return quality_score


def preprocess_image(image_path: str, target_size: Tuple[int, int] = (224, 224)) -> np.ndarray:
    """Preprocess image for MUSIQ input."""
    try:
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Resize image while maintaining aspect ratio
        image.thumbnail(target_size, Image.Resampling.LANCZOS)
        
        # Create a square image by padding if necessary
        new_image = Image.new('RGB', target_size, (0, 0, 0))
        paste_x = (target_size[0] - image.size[0]) // 2
        paste_y = (target_size[1] - image.size[1]) // 2
        new_image.paste(image, (paste_x, paste_y))
        
        # Convert to numpy array and normalize
        image_array = np.array(new_image, dtype=np.float32) / 255.0
        
        # Add batch dimension
        image_array = np.expand_dims(image_array, axis=0)
        
        return image_array
        
    except Exception as e:
        print(f"Error preprocessing image: {e}")
        return None


def load_model(checkpoint_path: Optional[str] = None):
    """Load or create MUSIQ model."""
    model = MUSIQTransformer()
    
    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"Loading model from {checkpoint_path}")
        model.load_weights(checkpoint_path)
    else:
        print("Creating model with random weights (no pretrained checkpoint)")
        # Initialize model with dummy input
        dummy_input = tf.random.normal([1, 224, 224, 3])
        _ = model(dummy_input, training=False)
    
    return model


def predict_image_quality(image_path: str, model=None, checkpoint_path: Optional[str] = None) -> float:
    """Predict image quality using MUSIQ model."""
    
    # Load model if not provided
    if model is None:
        model = load_model(checkpoint_path)
    
    # Preprocess image
    image_array = preprocess_image(image_path)
    if image_array is None:
        return -1.0
    
    # Make prediction
    quality_score = model(image_array, training=False)
    
    # Convert to scalar
    quality_score = float(quality_score[0, 0])
    
    return quality_score


def main():
    """Main function to run MUSIQ on a sample image."""
    parser = argparse.ArgumentParser(description='Run MUSIQ on a sample image')
    parser.add_argument('--image_path', type=str, default='../sample.jpg',
                       help='Path to the input image')
    parser.add_argument('--checkpoint_path', type=str, default=None,
                       help='Path to the model checkpoint')
    
    args = parser.parse_args()
    
    # Check if image exists
    if not os.path.exists(args.image_path):
        print(f"Error: Image file '{args.image_path}' not found")
        return
    
    print(f"Processing image: {args.image_path}")
    
    # Predict quality
    try:
        quality_score = predict_image_quality(args.image_path, checkpoint_path=args.checkpoint_path)
        
        if quality_score >= 0:
            print(f"Image Quality Score: {quality_score:.4f}")
            print("Note: This is a simplified implementation. For accurate results, use the full MUSIQ model with pretrained weights.")
            
            # Provide interpretation
            if quality_score >= 0.8:
                quality_level = "Excellent"
            elif quality_score >= 0.6:
                quality_level = "Good"
            elif quality_score >= 0.4:
                quality_level = "Fair"
            elif quality_score >= 0.2:
                quality_level = "Poor"
            else:
                quality_level = "Very Poor"
                
            print(f"Quality Assessment: {quality_level}")
        else:
            print("Error: Failed to process the image")
            
    except Exception as e:
        print(f"Error during prediction: {e}")


if __name__ == "__main__":
    main()
