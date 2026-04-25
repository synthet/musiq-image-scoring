
import os
import subprocess
import pytest
from firebird.driver import connect

FB_DLL = os.path.abspath(os.path.join("Firebird", "fbclient.dll"))
FB_DIR = os.path.dirname(FB_DLL)

@pytest.fixture
def basic_db_path():
    """Fixture that creates and cleans up a basic Firebird database."""
    import time
    import gc

    if not os.path.isfile(FB_DLL):
        pytest.skip("Firebird fbclient.dll not found under Firebird/")
    ISQL_EXE = os.path.join(FB_DIR, "isql.exe")
    if not os.path.isfile(ISQL_EXE):
        pytest.skip(f"Firebird isql.exe not found at {ISQL_EXE}")

    timestamp = int(time.time())
    db_path = os.path.abspath(f"TEST_basic_{timestamp}.fdb")
    
    print(f"Creating DB at: {db_path}")
    cmd = f"CREATE DATABASE '{db_path}' user 'SYSDBA' password 'masterkey'; EXIT;"
    
    env = os.environ.copy()
    env["FIREBIRD"] = FB_DIR
    if FB_DIR not in env["PATH"]:
        env["PATH"] += ";" + FB_DIR
        
    # Run isql
    res = subprocess.run([ISQL_EXE, '-q'], input=cmd.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    
    if res.returncode != 0:
        pytest.fail(f"ISQL Failed: {res.stderr.decode()}")
        
    if not os.path.exists(db_path):
         pytest.fail("DB File was not created")

    yield db_path

    # Teardown
    # Force garbage collection to release file handles
    gc.collect()
    
    # Retry removal with delays for Windows file locking
    for attempt in range(5):
        try:
            if os.path.exists(db_path):
                 os.remove(db_path)
            print("Cleaned up DB")
            break
        except Exception as e:
            if attempt < 4:
                time.sleep(0.5)
            else:
                print(f"Cleanup failed after 5 attempts: {e}")

@pytest.mark.firebird
def test_create_db_basic(basic_db_path):
    print(f"FB_DLL: {FB_DLL}")
    print(f"FB_DIR: {FB_DIR}")

    if not os.path.exists(FB_DLL):
        pytest.fail("fbclient.dll not found")

    db_path = basic_db_path
        
    assert os.path.exists(db_path), "DB File should exist"
    
    # Try to connect
    try:
        from firebird.driver import driver_config
        if hasattr(driver_config, 'fb_client_library'):
             driver_config.fb_client_library.value = FB_DLL

        con = connect(db_path, user='SYSDBA', password='masterkey')
        print("Successfully connected to DB")
        con.close()
    except Exception as e:
        pytest.fail(f"Connect failed: {e}")
