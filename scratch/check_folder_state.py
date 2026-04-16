
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.curdir))

from modules import db, config

def check_images():
    folder_path = "/mnt/d/Photos/Z8/180-600mm/2026/2026-04-09"
    print(f"Checking images in {folder_path}...")
    
    images = db.get_images_by_folder(folder_path)
    print(f"Found {len(images)} images in DB for this folder.")
    
    if not images:
        return
    
    # Check first 5 images
    for i, img in enumerate(images[:5]):
        print(f"\nImage {i+1}: {img['file_name']}")
        print(f"  ID: {img['id']}")
        print(f"  Thumbnail: {img['thumbnail_path']}")
        print(f"  Embedding key exists: {'image_embedding' in img}")
        print(f"  Embedding is null: {img.get('image_embedding') is None}")
        print(f"  Score General: {img.get('score_general')}")
    
    # Summary
    total = len(images)
    no_thumb = sum(1 for img in images if not img.get('thumbnail_path'))
    no_embedding = sum(1 for img in images if img.get('image_embedding') is None)
    
    print(f"\nSummary for {total} images:")
    print(f"  Images without thumbnails: {no_thumb}")
    print(f"  Images without embeddings: {no_embedding}")

if __name__ == "__main__":
    try:
        db.init_db()
        check_images()
    except Exception as e:
        print(f"Error: {e}")
