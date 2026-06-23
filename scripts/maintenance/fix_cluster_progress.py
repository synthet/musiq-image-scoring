
import os
import sys
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Configure Firebird Client Library Path
fb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Firebird")
if os.path.exists(fb_path):
    os.environ["PATH"] += ";" + fb_path
    os.environ["FIREBIRD"] = fb_path

try:
    from firebird.driver import connect, driver_config
except ImportError:
    print("Error: firebird-driver not installed.")
    sys.exit(1)

DB_FILE = "scoring_history.fdb"
db_path = os.path.abspath(DB_FILE)

def fix_db():
    print(f"Connecting to {db_path}...")
    try:
        conn = connect(database=db_path, user=os.environ.get("ISC_USER", "sysdba"), password=os.environ.get("ISC_PASSWORD", "masterkey"))
        cur = conn.cursor()
        
        # Check if table exists
        try:
            cur.execute("SELECT count(*) FROM cluster_progress")
            print("Table CLUSTER_PROGRESS already exists.")
        except Exception:
            print("Table CLUSTER_PROGRESS missing. Creating...")
            conn.rollback() # Clear error
            
            ddl = """
            CREATE TABLE cluster_progress (
                folder_path VARCHAR(4000) NOT NULL PRIMARY KEY,
                last_run TIMESTAMP
            )
            """
            cur.execute(ddl)
            conn.commit()
            print("Table CLUSTER_PROGRESS created successfully.")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_db()
