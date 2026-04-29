#!/usr/bin/env python3
"""
Example script demonstrating REST API usage for Vexlum Scoring (Web UI).

This script shows how to:
- Start a scoring job
- Monitor its progress
- Stop it if needed
- Check status of all runners
"""

import requests
import time
import json

BASE_URL = "http://127.0.0.1:7860/api"


def print_response(response):
    """Pretty print API response."""
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    except:
        print(f"Response: {response.text}")
    print()


def check_health():
    """Check if the API is available."""
    print("=== Health Check ===")
    response = requests.get(f"{BASE_URL}/health")
    print_response(response)
    return response.status_code == 200


def start_scoring(input_path, skip_existing=True):
    """Start a batch scoring job."""
    print(f"=== Starting Scoring Job ===")
    print(f"Input Path: {input_path}")
    
    response = requests.post(
        f"{BASE_URL}/scoring/start",
        json={
            "input_path": input_path,
            "skip_existing": skip_existing,
            "force_rescore": False
        }
    )
    print_response(response)
    return response.json() if response.status_code == 200 else None


def get_scoring_status():
    """Get current scoring status."""
    response = requests.get(f"{BASE_URL}/scoring/status")
    if response.status_code == 200:
        return response.json()
    return None


def monitor_scoring():
    """Monitor scoring progress until completion."""
    print("=== Monitoring Scoring Progress ===")
    
    while True:
        status = get_scoring_status()
        if not status:
            print("Failed to get status")
            break
        
        is_running = status.get("is_running", False)
        progress = status.get("progress", {})
        current = progress.get("current", 0)
        total = progress.get("total", 0)
        status_msg = status.get("status_message", "Unknown")
        
        if total > 0:
            pct = (current / total) * 100
            print(f"\rStatus: {status_msg} | Progress: {current}/{total} ({pct:.1f}%)", end="", flush=True)
        else:
            print(f"\rStatus: {status_msg}", end="", flush=True)
        
        if not is_running:
            print("\n=== Scoring Completed ===")
            print(f"Final Status: {status_msg}")
            if total > 0:
                print(f"Processed: {current}/{total} images")
            break
        
        time.sleep(2)  # Poll every 2 seconds


def stop_scoring():
    """Stop the running scoring job."""
    print("=== Stopping Scoring Job ===")
    response = requests.post(f"{BASE_URL}/scoring/stop")
    print_response(response)


def get_all_status():
    """Get status of all runners."""
    print("=== All Runners Status ===")
    response = requests.get(f"{BASE_URL}/status")
    print_response(response)


def score_single_image(file_path):
    """Score a single image."""
    print(f"=== Scoring Single Image ===")
    print(f"File: {file_path}")
    
    response = requests.post(
        f"{BASE_URL}/scoring/single",
        json={"file_path": file_path}
    )
    print_response(response)
    return response.json() if response.status_code == 200 else None


def get_recent_jobs(limit=5):
    """Get recent job history."""
    print(f"=== Recent Jobs (limit={limit}) ===")
    response = requests.get(f"{BASE_URL}/jobs/recent", params={"limit": limit})
    print_response(response)
    return response.json() if response.status_code == 200 else None


if __name__ == "__main__":
    import sys
    
    # Check health first
    if not check_health():
        print("API is not available. Make sure the webui is running.")
        sys.exit(1)
    
    # Example 1: Check all status
    get_all_status()
    
    # Example 2: Start scoring (uncomment to use)
    # result = start_scoring("D:/Photos/2024", skip_existing=True)
    # if result and result.get("success"):
    #     monitor_scoring()
    
    # Example 3: Score single image (uncomment to use)
    # score_single_image("D:/Photos/2024/image.jpg")
    
    # Example 4: Get recent jobs
    get_recent_jobs(limit=5)
    
    print("\n=== Examples Complete ===")
    print("Uncomment the examples above to try them out!")
