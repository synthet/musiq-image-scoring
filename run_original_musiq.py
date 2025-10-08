#!/usr/bin/env python3
"""
Script to run the original MUSIQ implementation on the sample image.
"""

import os
import sys
import subprocess
import argparse

def main():
    """Run original MUSIQ on the sample image."""
    
    parser = argparse.ArgumentParser(description='Run original MUSIQ on sample image')
    parser.add_argument('--image_path', type=str, default='sample.jpg',
                       help='Path to the input image')
    parser.add_argument('--checkpoint', type=str, default='spaq',
                       choices=['spaq', 'koniq', 'paq2piq', 'ava'],
                       help='Which checkpoint to use')
    
    args = parser.parse_args()
    
    # Check if sample image exists
    if not os.path.exists(args.image_path):
        print(f"Error: Sample image '{args.image_path}' not found in current directory")
        print("Available files:")
        for file in os.listdir("."):
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
                print(f"  - {file}")
        return
    
    # Check if virtual environment exists
    venv_python = "musiq_env/Scripts/python.exe"
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please run the installation first.")
        return
    
    # Set checkpoint path
    checkpoint_path = f"musiq_original/checkpoints/{args.checkpoint}_ckpt.npz"
    if not os.path.exists(checkpoint_path):
        print(f"Error: Checkpoint file '{checkpoint_path}' not found")
        print("Available checkpoints:")
        checkpoint_dir = "musiq_original/checkpoints"
        if os.path.exists(checkpoint_dir):
            for file in os.listdir(checkpoint_dir):
                if file.endswith('.npz'):
                    print(f"  - {file}")
        return
    
    print("=" * 60)
    print("Running ORIGINAL MUSIQ on sample image...")
    print(f"Image: {args.image_path}")
    print(f"Checkpoint: {args.checkpoint} ({checkpoint_path})")
    print("=" * 60)
    
    try:
        # Run the fixed MUSIQ script from within the musiq_original directory
        cmd = [
            venv_python, 
            "run_predict_image_fixed.py",
            "--ckpt_path", checkpoint_path,
            "--image_path", f"../{args.image_path}"
        ]
        
        # Change to musiq_original directory and run from there
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="musiq_original")
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        if result.returncode != 0:
            print(f"Process exited with code {result.returncode}")
            print("\nTroubleshooting:")
            print("1. Make sure all dependencies are installed")
            print("2. Check that the checkpoint file is valid")
            print("3. Verify the image file is readable")
            
    except Exception as e:
        print(f"Error running original MUSIQ: {e}")
    
    print("=" * 60)
    print("Original MUSIQ analysis complete!")


if __name__ == "__main__":
    main()
