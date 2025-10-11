#!/usr/bin/env python3
"""
Phase 2 Project Restructuring - Organize Remaining Root Files

Moves remaining Python scripts and utility files from root to appropriate subdirectories.
"""

import shutil
from pathlib import Path

# Phase 2 file movements
PHASE2_MOVES = {
    # Python entry points/libraries
    "scripts/python": [
        "run_vila.py",
        "gallery_generator.py",
        "batch_process_images.py",
        "run_musiq.py",
        "run_musiq_simple.py",
        "run_musiq_gpu.py",
        "run_tfhub_musiq.py",
        "run_original_musiq.py",
    ],
    
    # Analysis and scoring scripts
    "scripts/analysis": [
        "analyze_json_results.py",
        "compare_scoring_methods.py",
        "weighted_scoring_strategy.py",
        "monitor_progress.py",
    ],
    
    # Setup scripts
    "scripts/setup": [
        "setup_gpu.py",
        "setup_wsl2_simple.py",
        "setup_wsl2_tensorflow_gpu.py",
        "simple_gpu_setup.py",
        "gpu_detection.py",
    ],
    
    # Maintenance/helper scripts
    "scripts/maintenance": [
        "restructure_project.py",
        "update_references.py",
        "update_all_references.py",
    ],
    
    # Documentation (restructuring docs)
    "docs/technical": [
        "RESTRUCTURE_PLAN.md",
        "PROJECT_STRUCTURE.md",
        "RESTRUCTURE_SUMMARY.md",
    ],
}

# Files to KEEP in root (essentials only)
ROOT_ESSENTIALS = [
    "README.md",
    "CHANGELOG.md",
    "INDEX.md",
    "requirements.txt",
    ".gitignore",
    "run_all_musiq_models.py",  # Main entry point
    "create_gallery.bat",        # Main user wrapper
    "Create-Gallery.ps1",        # Main user wrapper
    "test_model_sources.bat",    # Common test wrapper
    "image_gallery.html",        # Output example
]


def move_file(src: str, dest_dir: str, dry_run: bool = False):
    """Move a file to destination directory."""
    src_path = Path(src)
    if not src_path.exists():
        print(f"  ⚠️  File not found: {src}")
        return False
    
    dest_path = Path(dest_dir) / src_path.name
    
    if dry_run:
        print(f"  Would move: {src} -> {dest_path}")
        return True
    
    try:
        shutil.move(str(src_path), str(dest_path))
        print(f"  ✓ Moved: {src} -> {dest_path}")
        return True
    except Exception as e:
        print(f"  ✗ Error moving {src}: {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Phase 2 restructuring")
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without doing it')
    args = parser.parse_args()
    
    print("=" * 70)
    print("PHASE 2 PROJECT RESTRUCTURING")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    moved_count = 0
    error_count = 0
    
    for dest_dir, files in PHASE2_MOVES.items():
        print(f"\n→ Moving to {dest_dir}/:")
        for file in files:
            if move_file(file, dest_dir, args.dry_run):
                moved_count += 1
            else:
                error_count += 1
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files moved: {moved_count}")
    print(f"Errors: {error_count}")
    
    if not args.dry_run:
        print("\n✓ Phase 2 restructuring complete!")
        print("\nFiles remaining in root (essentials only):")
        for file in sorted(ROOT_ESSENTIALS):
            if Path(file).exists():
                print(f"  ✓ {file}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

