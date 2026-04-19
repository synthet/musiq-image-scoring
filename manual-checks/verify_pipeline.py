
import threading
import time
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from unittest.mock import MagicMock
tf_mock = MagicMock()
sys.modules["tensorflow"] = tf_mock
sys.modules["scripts.python.run_all_musiq_models"] = MagicMock()
sys.modules["modules.scoring"] = MagicMock()
sys.modules["modules.thumbnails"] = MagicMock()
sys.modules["modules.exif_extractor"] = MagicMock()
sys.modules["modules.xmp"] = MagicMock()

# Mock MultiModelMUSIQ before it's imported
from unittest.mock import patch
mock_musiq = MagicMock()
sys.modules["modules.scoring"].MultiModelMUSIQ = mock_musiq

from modules.pipeline import ImageJob, PrepWorker, ScoringWorker, ResultWorker
import queue

# Dummy Scorer
class DummyScorer:
    VERSION = "3.0.0"
    def is_raw_file(self, path):
        return path.endswith(".nef")
    
    def convert_raw_to_jpeg(self, path):
        return path + ".jpg" # Fake
    
    def run_all_models(self, path, external_scores=None, logger=None, write_metadata=False):
        time.sleep(0.1)
        return {
            "summary": {
                "failed_predictions": 0,
                "total_models": 1,
                "weighted_scores": {"general": 0.85}
            },
            "models": {}
        }

def test_pipeline():
    print("Testing Pipeline...")
    
    prep_q = queue.Queue()
    score_q = queue.Queue()
    result_q = queue.Queue()
    stop_event = threading.Event()
    
    scorer = DummyScorer()
    # Mocking metadata methods
    scorer.score_to_rating = MagicMock(return_value=5)
    scorer.determine_lightroom_label = MagicMock(return_value="Green")
    scorer.write_metadata_to_nef = MagicMock(return_value=True)
    
    # Init Workers
    prep = PrepWorker(prep_q, score_q, stop_event, scorer)
    score = ScoringWorker(score_q, result_q, stop_event, scorer)
    
    def log_res(msg):
        print(f"Callback: {msg}")
    
    dummy_out = queue.Queue()
    result_worker_inst = ResultWorker(result_q, dummy_out, stop_event, scorer_instance=scorer, progress_callback=log_res)
    
    workers = [prep, score, result_worker_inst]
    for w in workers: w.start()
    
    # Fake DB
    import modules.db as db
    original_upsert = db.upsert_image
    db.upsert_image = lambda j, r: print(f"DB Upsert: {j}")
    original_exists = db.image_exists
    db.image_exists = lambda p, current_version=None: False
    
    # Feed
    job = ImageJob("test_image.jpg", 1)
    prep_q.put(job)
    
    job_raw = ImageJob("test_raw.nef", 1)
    prep_q.put(job_raw)
    
    # Wait
    prep_q.put(None)
    prep.join()
    score_q.put(None)
    score.join()
    result_q.put(None)
    result_worker_inst.join()
    
    print("Test Finished.")
    
    # Verify Metadata Call
    print(f"Write Metadata Called: {scorer.write_metadata_to_nef.called}")

if __name__ == "__main__":
    test_pipeline()
