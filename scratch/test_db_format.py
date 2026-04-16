
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from modules import db, utils

def test():
    try:
        conn = db.get_connector()
        print(f"Connector type: {conn.type}")
        
        rows = conn.query("SELECT id, file_path FROM images LIMIT 1")
        print(f"Rows type: {type(rows)}")
        if rows:
            row = rows[0]
            print(f"Row type: {type(row)}")
            print(f"Row data: {row}")
            
            image_id = row["id"]
            file_path = row["file_path"]
            print(f"image_id type: {type(image_id)}, value: {image_id}")
            print(f"file_path type: {type(file_path)}, value: {file_path}")
            
            resolved = utils.resolve_file_path(file_path, image_id)
            print(f"Resolved path: {resolved}")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
