from modules import db
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_neighbors():
    # Find some image IDs to test with
    connector = db.get_connector()
    res = connector.query("SELECT id, folder_id FROM images LIMIT 5")
    if not res:
        print("No images in DB to test.")
        return
    
    for row in res:
        img_id = row['id']
        print(f"\nTesting neighbors for Image ID: {img_id}")
        
        # Test default sort (score desc)
        prev_id, next_id = db.get_image_neighbors(img_id, sort_by="score_general", order="desc")
        print(f"Default Sort (score_general desc): prev={prev_id}, next={next_id}")
        
        # Test ID sort (asc)
        prev_id, next_id = db.get_image_neighbors(img_id, sort_by="id", order="asc")
        print(f"ID Sort (asc): prev={prev_id}, next={next_id}")

if __name__ == "__main__":
    test_neighbors()
