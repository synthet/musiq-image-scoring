
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

import pytest
from modules import db


@pytest.mark.db
def test_export_db_to_json():
    output_file = "test_export.json"

    if os.path.exists(output_file):
        os.remove(output_file)

    print("Testing export_db_to_json...")
    success, msg = db.export_db_to_json(output_file)

    print(f"Success: {success}")
    print(f"Message: {msg}")

    # Add assertions for pytest
    if "pytest" in sys.modules:
        assert success, f"Export failed: {msg}"
        assert os.path.exists(output_file), "Output file was not created"
    
    if success and os.path.exists(output_file):
        print("Verification PASSED: File created.")
        # Validation
        import json
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"Record count: {len(data)}")
        
        # Cleanup if successful
        if "pytest" in sys.modules:
             os.remove(output_file)
    else:
        print("Verification FAILED.")

if __name__ == "__main__":
    test_export_db_to_json()

