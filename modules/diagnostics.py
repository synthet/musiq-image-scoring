import os
import platform
import sys
import shutil
import logging
from typing import Dict, Any, List
import datetime

# Internal modules
from modules import config, db

logger = logging.getLogger(__name__)

def get_diagnostics() -> Dict[str, Any]:
    """Collect comprehensive system and application diagnostics data."""
    
    # 1. System Information
    system_info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "cpu_count": os.cpu_count(),
    }
    
    # Try to get memory info if psutil is available
    try:
        import psutil
        mem = psutil.virtual_memory()
        system_info["memory_total_gb"] = round(mem.total / (1024**3), 2)
        system_info["memory_available_gb"] = round(mem.available / (1024**3), 2)
        system_info["memory_percent"] = mem.percent
    except ImportError:
        system_info["memory_info"] = "psutil not available"

    # 2. Database Information
    engine = config.get_database_engine()
    db_info = {
        "type": engine.capitalize(),
        "reachable": False,
        "size_mb": 0,
    }
    
    if engine == "postgres":
        pg_conf = config.get_config_section("database").get("postgres", {})
        db_info["path"] = f"{pg_conf.get('host')}:{pg_conf.get('port')}/{pg_conf.get('dbname')}"
    else:
        db_info["path"] = os.environ.get("FIREBIRD_DATABASE", "SCORING_HISTORY.FDB")

    try:
        conn = db.get_db()
        db_info["reachable"] = True
        conn.close()
        
        # Metadata for local files (Firebird/SQLite)
        if engine == "firebird" or engine == "sqlite":
            db_path = db_info["path"]
            if os.path.exists(db_path):
                db_info["size_mb"] = round(os.path.getsize(db_path) / (1024**2), 2)
                db_info["last_modified"] = datetime.datetime.fromtimestamp(
                    os.path.getmtime(db_path)
                ).isoformat()
        else:
            # For Postgres, we might want to query DB size, but for now leave as 0
            # or just skip file stats
            db_info["last_modified"] = datetime.datetime.now().isoformat() # Placeholder for now
    except Exception as e:
        db_info["error"] = str(e)

    # 3. Model & GPU Information
    model_info = {
        "gpu_available": False,
        "frameworks": [],
    }
    
    # Check TensorFlow
    try:
        import tensorflow as tf
        model_info["frameworks"].append(f"TensorFlow {tf.__version__}")
        try:
            gpus = tf.config.list_physical_devices('GPU')
            if gpus:
                model_info["gpu_available"] = True
                model_info["tf_gpus"] = [str(g) for g in gpus]
        except Exception as e:
            model_info["tf_gpu_error"] = str(e)
    except (ImportError, Exception) as e:
        if not isinstance(e, ImportError):
            model_info["frameworks"].append(f"TensorFlow (Broken: {str(e)[:50]})")

    # Check PyTorch
    try:
        import torch
        model_info["frameworks"].append(f"PyTorch {torch.__version__}")
        try:
            if torch.cuda.is_available():
                model_info["gpu_available"] = True
                model_info["torch_gpu_name"] = torch.cuda.get_device_name(0)
                model_info["cuda_version"] = torch.version.cuda
        except Exception as e:
            model_info["torch_gpu_error"] = str(e)
    except (ImportError, Exception) as e:
        if not isinstance(e, ImportError):
            model_info["frameworks"].append(f"PyTorch (Broken: {str(e)[:50]})")

    # 4. FileSystem Information
    fs_info = {
        "root_dir": os.path.abspath("."),
        "thumbnails_dir": str(config.BASE_DIR / "thumbnails"),
        "free_space_gb": 0,
    }
    
    try:
        total, used, free = shutil.disk_usage(".")
        fs_info["free_space_gb"] = round(free / (1024**3), 2)
        fs_info["total_space_gb"] = round(total / (1024**3), 2)
    except Exception:
        pass

    # 5. Configuration Summary (Masked)
    try:
        app_config = config.load_config()
        # Create a safe summary of config (excluding secrets if any)
        config_summary = {
            "debug": app_config.get("debug", False),
            "webui_port": app_config.get("webui_port", 7860),
            "allowed_paths_count": len(app_config.get("system", {}).get("allowed_paths", [])),
        }
    except Exception:
        config_summary = {"error": "Could not load config"}

    # 6. Runner Status (Mocked/Static for now, will get from global state if integrated)
    # This will be updated in api.py where global runners are available
    
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "system": system_info,
        "database": db_info,
        "models": model_info,
        "filesystem": fs_info,
        "config": config_summary,
    }
