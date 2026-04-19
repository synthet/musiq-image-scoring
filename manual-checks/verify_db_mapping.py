
import sqlite3
import json
import os
import sys

# Add modules to path
sys.path.insert(0, os.getcwd())
try:
    from modules import db
except ImportError:
    # If running from tests/ might act weird with cwd
    sys.path.insert(0, os.path.dirname(os.getcwd()))
    from modules import db

def test_upsert_mapping():
    # 1. Setup InMemory DB with schema
    # We can't easily mock get_db unless we monkeypatch it or use a test DB file.
    # db.py uses DB_FILE global. We can patch it.
    
    test_db = "test_verify.db"
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except: pass
        
    db.DB_FILE = test_db
    db.init_db()
    
    # 2. Prepare Data (User's failing case)
    payload = {
        "image_path": "/path/to/image.nef",
        "image_name": "image.nef",
        "models": {
            "spaq": {
                "score": 52.67,
                "normalized_score": 0.527,
                "status": "success"
            },
            "ava": {
                "score": 4.57,
                "normalized_score": 0.396,
                "status": "success"
            },
            "koniq": {
                "score": 63.85,
                "normalized_score": 0.639,
                "status": "success"
            },
            "paq2piq": {
                "score": 73.2,
                "normalized_score": 0.732,
                "status": "success"
            }
        },
        "summary": {
            "weighted_scores": {
                "technical": 0.441,
                "aesthetic": 0.463,
                "general": 0.439
            },
            "average_normalized_score": 0.439
        },
        # Simulate the injection done by ResultWorker
        "nef_metadata": {
            "rating": 4,
            "label": "Blue"
        }
    }
    
    # 3. Call Upsert
    try:
        db.upsert_image(job_id=1, result=payload)
    except Exception as e:
        print(f"Upsert crashed: {e}")
        sys.exit(1)
    
    # 4. Verify
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM images WHERE file_path = ?", ("/path/to/image.nef",))
    row = c.fetchone()
    
    if not row:
        print("FAIL: No row inserted.")
        sys.exit(1)
        
    print("Verifying Database Records...")
    errors = 0
    
    # Check Individual Scores
    expectations = {
        "score_spaq": 0.527,
        "score_ava": 0.396,
        "score_koniq": 0.639,
        "score_paq2piq": 0.732,
        "rating": 4,
        "label": "Blue",
        "score_general": 0.439
    }
    
    for col, expected in expectations.items():
        actual = row[col]
        # Handle None if not inserted
        if actual is None:
            if isinstance(expected, (int, float)):
                actual = 0
            else:
                actual = ""
            
        if isinstance(expected, (int, float)):
            if abs(actual - expected) > 0.001:
                print(f"FAIL: {col} expected {expected}, got {actual}")
                errors += 1
            else:
                print(f"PASS: {col} = {actual}")
        else:
            if actual != expected:
               print(f"FAIL: {col} expected {expected}, got {actual}")
               errors += 1
            else:
               print(f"PASS: {col} = {actual}")

    conn.close()
    
    # Cleanup
    if os.path.exists(test_db):
        try:
           os.remove(test_db)
        except: pass
        
    if errors == 0:
        print("SUCCESS: All mappings correct.")
    else:
        print(f"FAILURE: {errors} errors found.")
        sys.exit(1)

if __name__ == "__main__":
    test_upsert_mapping()
