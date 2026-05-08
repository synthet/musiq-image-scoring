import os
import subprocess
import requests
import json
from pathlib import Path

# Curated public NEF sample URLs
PUBLIC_SAMPLES = {
    "D90": {
        "filename": "RAW_NIKON_D90.NEF",
        "url": "http://www.rawsamples.ch/raws/nikon/d90/RAW_NIKON_D90.NEF",
        "source": "rawsamples.ch"
    },
    "D300": {
        "filename": "RAW_NIKON_D300.NEF",
        "url": "http://www.rawsamples.ch/raws/nikon/d300/RAW_NIKON_D300.NEF",
        "source": "rawsamples.ch"
    },
    "Z6II": {
        "filename": "nikon_z6_ii_01.nef",
        "url": "https://img.photographyblog.com/reviews/nikon_z6_ii/sample_images/nikon_z6_ii_01.nef",
        "source": "photographyblog.com"
    },
    "Z8": {
        "filename": "nikon_z8_01.nef",
        "url": "https://img.photographyblog.com/reviews/nikon_z8/sample_images/nikon_z8_01.nef",
        "source": "photographyblog.com"
    }
}

DEST_DIR = Path("tests/fixtures/testing_samples/public")

def download_file(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Create parent directories if they don't exist
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        done = int(50 * downloaded / total_size)
                        print(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded}/{total_size} bytes", end='')
        print("\nDownload complete.")
        
        # Store source URL in EXIF/XMP
        print(f"Storing source URL in metadata for {dest_path}...")
        subprocess.run([
            "exiftool",
            "-overwrite_original",
            f"-XMP-dc:Source={url}",
            f"-Comment=Source: {url}",
            str(dest_path)
        ], capture_output=True)
        
        return True
    except Exception as e:
        print(f"\nFailed to download {url}: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Download public Nikon RAW samples.")
    parser.add_argument("--force", action="store_true", help="Force download even if files exist.")
    args = parser.parse_args()

    if not DEST_DIR.exists():
        DEST_DIR.mkdir(parents=True)
        
    manifest_path = DEST_DIR / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            
    for model, info in PUBLIC_SAMPLES.items():
        dest_path = DEST_DIR / model / info['filename']
        if dest_path.exists() and not args.force:
            print(f"Sample for {model} already exists at {dest_path}")
        else:
            if download_file(info['url'], dest_path):
                manifest[f"{model}/{info['filename']}"] = {
                    "source": info['source'],
                    "url": info['url'],
                    "model": model
                }
                
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Updated manifest at {manifest_path}")

if __name__ == "__main__":
    main()
