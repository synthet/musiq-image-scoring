#!/usr/bin/env python3
"""
Monitor batch processing progress by checking JSON files and log updates.
"""

import os
import time
import glob
from datetime import datetime

def monitor_progress(directory: str, log_file: str = None):
    """Monitor batch processing progress."""
    print(f"Monitoring progress in: {directory}")
    print("=" * 60)
    
    # Find the latest log file if not specified
    if log_file is None:
        log_files = glob.glob(os.path.join(directory, "musiq_batch_log_*.log"))
        if log_files:
            log_file = max(log_files, key=os.path.getmtime)
            print(f"Using log file: {os.path.basename(log_file)}")
        else:
            print("No log file found!")
            return
    
    last_json_count = 0
    last_log_size = 0
    
    while True:
        try:
            # Count JSON files
            json_files = glob.glob(os.path.join(directory, "*.json"))
            json_count = len(json_files)
            
            # Check log file size
            if os.path.exists(log_file):
                log_size = os.path.getsize(log_file)
                
                # Read last few lines of log
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    last_lines = lines[-5:] if len(lines) >= 5 else lines
                
                # Check if processing is complete
                if any("BATCH PROCESSING COMPLETED" in line for line in lines):
                    print(f"\n✅ Batch processing completed!")
                    print(f"Total JSON files created: {json_count}")
                    break
                
                # Show progress if there are changes
                if json_count != last_json_count or log_size != last_log_size:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] JSON files: {json_count}")
                    
                    if last_lines:
                        last_line = last_lines[-1].strip()
                        if last_line:
                            print(f"  Latest: {last_line}")
                    
                    last_json_count = json_count
                    last_log_size = log_size
                
            else:
                print("Log file not found, waiting...")
            
            time.sleep(10)  # Check every 10 seconds
            
        except KeyboardInterrupt:
            print(f"\nMonitoring stopped. Current JSON files: {json_count}")
            break
        except Exception as e:
            print(f"Error monitoring: {e}")
            time.sleep(5)

if __name__ == "__main__":
    import sys
    
    directory = sys.argv[1] if len(sys.argv) > 1 else "D:/Photos/Export/2025"
    log_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    monitor_progress(directory, log_file)
