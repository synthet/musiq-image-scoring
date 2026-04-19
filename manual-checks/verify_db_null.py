import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from modules.db import upsert_image, get_db

def test_db_null_handling():
    # Use 0 or None for job_id
    job_id = 0
    
    # Mock result with a failed LIQE score and a successful SPAQ score
    image_path = os.path.abspath("test_verify_null.jpg")
    result = {
        "image_path": image_path,
        "status": "success",
        "models": {
            "liqe": {
                "status": "failed",
                "error": "Simulated failure"
            },
            "spaq": {
                "status": "success",
                "score": 0.5,
                "normalized_score": 0.5
            }
        },
        "score_general": 0.5,
        "score_technical": 0.5,
        "score_aesthetic": 0.5
    }
    
    print(f"Upserting image '{image_path}' with failed LIQE score...")
    upsert_image(job_id, result)
    
    # Query the database to check the value
    print("Checking database value for SCORE_LIQE...")
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT SCORE_LIQE, SCORE_SPAQ FROM IMAGES WHERE FILE_PATH = ?"
    cursor.execute(query, (image_path,))
    row = cursor.fetchone()
    
    if row:
        liqe_val = row[0]
        spaq_val = row[1]
        print(f"Database values: SCORE_LIQE={liqe_val}, SCORE_SPAQ={spaq_val}")
        if liqe_val is None:
            print("SUCCESS: SCORE_LIQE is NULL as expected.")
        else:
            print(f"FAILURE: SCORE_LIQE is {liqe_val}, expected NULL.")
    else:
        print("FAILURE: Image not found in database.")
    
    # Cleanup
    # db.execute_query("DELETE FROM IMAGES WHERE FILE_PATH = ?", (image_path,))

if __name__ == "__main__":
    test_db_null_handling()
