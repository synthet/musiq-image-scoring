
import os
import sys
import shutil
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from modules.culling import CullingEngine

def verify_fix():
    print("Verifying Culling Fix...")
    
    # 1. Setup DB
    template_db = os.path.abspath("template.fdb")
    if not os.path.exists(template_db):
        print("Error: template.fdb missing")
        return False
        
    timestamp = int(time.time())
    db_path = os.path.abspath(f"TEST_ver_cull_{timestamp}.fdb")
    print(f"Using DB: {db_path}")
    
    try:
        shutil.copy2(template_db, db_path)
    except Exception as e:
        # Fallback to shell copy if shutil crashes here too (unlikely in pure script)
        os.system(f'copy "{template_db}" "{db_path}"')
        
    db.DB_PATH = db_path
    
    # 2. Init DB
    try:
        db.init_db()
        print("DB Initialized")
    except Exception as e:
        print(f"DB Init Failed: {e}")
        return False

    # 3. Create Session
    try:
        engine = CullingEngine()
        test_folder = os.path.abspath("temp_verify_cull")
        if not os.path.exists(test_folder):
            os.makedirs(test_folder)
            
        print("Creating culling session...")
        # This calls db.create_culling_session internally
        session_id = engine.create_session(test_folder, mode='automated')
        
        print(f"Session Created. ID: {session_id}")
        
        with open("verify_result.txt", "w") as f:
            if session_id and session_id > 0:
                f.write("SUCCESS")
            else:
                f.write("FAILURE: ID Invalid")
                
        if session_id and session_id > 0:
            print("SUCCESS: Culling session created without AttributeError")
        else:
            print("FAILURE: Session ID invalid")
            return False
            
    except AttributeError as e:
        with open("verify_result.txt", "w") as f:
            f.write(f"FAILURE: AttributeError: {e}")
        print(f"FAILURE: AttributeError detected: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        with open("verify_result.txt", "w") as f:
            f.write(f"FAILURE: Exception: {e}")
        print(f"FAILURE: Other error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        try:
            db.get_db().close()
        except: pass
        
        # Cleanup file
        # time.sleep(1)
        if os.path.exists(db_path):
            import gc
            gc.collect()
            try:
                os.remove(db_path)
                print(f"Cleaned up {db_path}")
            except Exception as e:
                print(f"Warning: Could not remove {db_path}: {e}")
        
        # Cleanup result file
        if os.path.exists("verify_result.txt"):
             try:
                 os.remove("verify_result.txt")
                 print("Cleaned up verify_result.txt")
             except: pass
        pass

    return True

if __name__ == "__main__":
    if verify_fix():
        sys.exit(0)
    else:
        sys.exit(1)
