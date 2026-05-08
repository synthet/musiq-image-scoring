import os
import subprocess
import argparse
from pathlib import Path

def generate_base_tiff(output_path):
    """Generates a tiny 10x10 black TIFF as a base for the NEF."""
    from PIL import Image
    img = Image.new('RGB', (10, 10), color=0)
    img.save(output_path, format='TIFF')

def apply_nikon_tags(file_path, model, lens=None, focal_length=None):
    """Uses exiftool to apply Nikon-specific tags to the file."""
    cmd = [
        "exiftool",
        "-overwrite_original",
        f"-Make=NIKON CORPORATION",
        f"-Model=NIKON {model}",
    ]
    
    if lens:
        cmd.append(f"-Lens={lens}")
        cmd.append(f"-LensModel={lens}")
        cmd.append(f"-LensInfo={lens}")
    
    if focal_length:
        cmd.append(f"-FocalLength={focal_length}")
        cmd.append(f"-FocalLengthIn35mmFormat={focal_length}")

    # Nikon MakerNote specific tags (simulated)
    cmd.extend([
        "-Nikon:ColorSpace=sRGB",
        "-Nikon:Quality=RAW",
        "-Nikon:WhiteBalance=Auto",
        "-Nikon:FocusMode=AF-S",
        "-Nikon:LensType=D G VR",
        "-DateTimeOriginal=2024:05:07 12:00:00",
        "-CreateDate=2024:05:07 12:00:00",
    ])
    
    cmd.append(file_path)
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error applying tags: {result.stderr}")
    else:
        print(f"Successfully applied tags to {file_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic Nikon NEF files for testing.")
    parser.add_argument("--model", required=True, help="Camera model (e.g., D90, Z8)")
    parser.add_argument("--lens", help="Lens name")
    parser.add_argument("--focal", help="Focal length")
    parser.add_argument("--output", help="Output filename")
    
    args = parser.parse_args()
    
    output_dir = Path("tests/fixtures/testing_samples/synthetic")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = args.output or f"SYNTHETIC_{args.model.replace(' ', '_')}.NEF"
    dest_path = output_dir / filename
    
    # 1. Generate base TIFF
    temp_tiff = dest_path.with_suffix(".tiff")
    generate_base_tiff(temp_tiff)
    
    # 2. Rename to .NEF
    if dest_path.exists():
        dest_path.unlink()
    temp_tiff.rename(dest_path)
    
    # 3. Apply Nikon tags
    apply_nikon_tags(str(dest_path), args.model, args.lens, args.focal)
    
    print(f"Generated synthetic NEF at {dest_path}")

if __name__ == "__main__":
    main()
