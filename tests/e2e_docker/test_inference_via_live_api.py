import os
import time
import pytest

# Skip if running locally without Docker E2E opt-in
pytestmark = [
    pytest.mark.inference_e2e,
    pytest.mark.postgres,
    pytest.mark.ml,
    pytest.mark.gpu,
    pytest.mark.sample_data,
]

@pytest.mark.skipif(
    os.environ.get("IMAGE_SCORING_DOCKER_INFERENCE_E2E") != "1",
    reason="Requires Docker E2E environment (IMAGE_SCORING_DOCKER_INFERENCE_E2E=1)",
)
def test_inference_via_live_api():
    """
    Opt-in GPU-backed end-to-end path running inside the CUDA Docker image.
    Targets isolated PostgreSQL database, starts the real FastAPI/Gradio stack,
    and drives jobs via HTTP, asserting on results.
    
    Run via compose:
    docker compose --profile e2e-inference run --rm inference-e2e
    """
    # httpx must be imported locally or as part of test suite dependencies
    httpx = pytest.importorskip("httpx")
    from modules import db

    base_url = os.environ.get("E2E_WEBUI_URL", "http://127.0.0.1:7860")
    
    # We use httpx to perform real HTTP requests against the webui process started by the script
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        # Submit the job
        payload = {
            "scope_type": "folder_recursive",
            # The test fixtures path mapped in the container
            "scope_paths": ["/app/tests/fixtures/testing_samples"],
            "stages": ["indexing", "metadata", "scoring"],
            "run_mode": "process_unprocessed_or_empty",
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
            "validation_repair_dry_run": False,
            "generate_captions": False,
        }
        
        r = client.post("/api/runs/submit", json=payload)
        assert r.status_code == 200, f"Submit failed: {r.text}"
        data = r.json()
        assert data.get("success") is True, f"Submit unsuccessful: {data}"
        run_id = data.get("run_id")
        assert run_id is not None
        
        # Poll for completion
        deadline = time.time() + 600.0  # 10 minutes max for cold load + processing
        status = "queued"
        
        while time.time() < deadline:
            r = client.get("/api/jobs/recent")
            assert r.status_code == 200
            jobs = r.json().get("jobs", [])
            job = next((j for j in jobs if j.get("id") == int(run_id)), None)
            
            if job:
                status = str(job.get("status") or "").lower()
                if status in ("completed", "failed", "cancelled"):
                    break
            
            time.sleep(5.0)
            
        assert status == "completed", f"Job failed to complete in time. Last status: {status}"
        
        # Assert scores were written by checking the database directly
        images = db.execute_query("SELECT id, file_path, general_score, technical_score FROM images WHERE file_path LIKE ?", ('%testing_samples%',))
        
        assert len(images) > 0, "No images found in the database after processing"
        
        scored_images = [img for img in images if img.get("general_score") is not None]
        assert len(scored_images) > 0, "No images have been scored"
        
        for img in scored_images:
            assert float(img["general_score"]) > 0, f"Image {img['file_path']} has invalid general_score: {img['general_score']}"
            assert float(img["technical_score"]) > 0, f"Image {img['file_path']} has invalid technical_score: {img['technical_score']}"
