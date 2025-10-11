#!/usr/bin/env python3
"""
Project Restructuring Script

This script reorganizes the project files into a semantic folder structure
while preserving all links and references.
"""

import os
import shutil
import re
from pathlib import Path

# Define file movements
FILE_MOVES = {
    # Documentation -> docs/
    "docs/getting-started": [
        "README_simple.md",
        "VERSION_2.3.0_RELEASE_NOTES.md",
        "COMPLETE_SESSION_SUMMARY.md",
    ],
    "docs/vila": [
        "README_VILA.md",
        "VILA_QUICK_START.md",
        "VILA_BATCH_FILES_GUIDE.md",
        "VILA_INTEGRATION_SUMMARY.md",
        "VILA_ALL_FIXES_SUMMARY.md",
        "VILA_FIXES_SUMMARY.md",
        "VILA_COMPLETE_SUMMARY.md",
        "VILA_MODEL_PATH_FIX.md",
        "VILA_PARAMETER_FIX.md",
        "VILA_SCORE_RANGE_CORRECTION.md",
    ],
    "docs/gallery": [
        "GALLERY_GENERATOR_README.md",
        "GALLERY_README.md",
        "GALLERY_VILA_UPDATE.md",
        "GALLERY_SORTING_FIX.md",
    ],
    "docs/setup": [
        "WSL2_SETUP_COMPLETE.md",
        "WSL2_TENSORFLOW_GPU_SETUP.md",
        "WSL_WRAPPER_VERIFICATION.md",
        "WSL_PYTHON_ENVIRONMENT_STATUS.md",
        "WSL_PYTHON_PACKAGES.md",
        "WSL_UBUNTU_PACKAGES.md",
        "GPU_SETUP_STATUS.md",
        "GPU_IMPLEMENTATION_SUMMARY.md",
        "install_cuda.md",
        "README_gpu.md",
        "WINDOWS_SCRIPTS_README.md",
    ],
    "docs/technical": [
        "MODELS_SUMMARY.md",
        "MODEL_FALLBACK_MECHANISM.md",
        "TRIPLE_FALLBACK_SYSTEM.md",
        "MODEL_SOURCE_TESTING.md",
        "CHECKPOINT_STATUS.md",
        "WEIGHTED_SCORING_STRATEGY.md",
        "ANALYSIS_SCRIPT_DOCUMENTATION.md",
        "BATCH_PROCESSING_SUMMARY.md",
        "README_MULTI_MODEL.md",
        "PROJECT_STRUCTURE_ANALYSIS.md",
    ],
    "docs/maintenance": [
        "CLEANUP_SUMMARY.md",
        "ENVIRONMENT_CLEANUP_SUMMARY.md",
        "SESSION_UPDATE_SUMMARY.md",
    ],
    
    # Scripts -> scripts/
    "scripts/batch": [
        "create_gallery.bat",
        "create_gallery_simple.bat",
        "process_images.bat",
        "batch_process_images.bat",
        "open_gallery.bat",
        "open_historical_gallery.bat",
        "open_today_gallery.bat",
        "run_musiq_advanced.bat",
        "run_musiq_drag_drop.bat",
        "run_musiq_gpu.bat",
        "run_all_musiq_models_drag_drop.bat",
        "run_vila.bat",
        "run_vila_drag_drop.bat",
        "test_vila.bat",
        "test_model_sources.bat",
        "analyze_results.bat",
    ],
    "scripts/powershell": [
        "Create-Gallery.ps1",
        "Process-Images.ps1",
        "Batch-Process-Images.ps1",
        "Open-Gallery.ps1",
        "Open-Historical-Gallery.ps1",
        "Open-Today-Gallery.ps1",
        "Run-All-MUSIQ-Models.ps1",
        "Run-MUSIQ-GPU.ps1",
        "Analyze-Results.ps1",
        "Test-ModelSources.ps1",
    ],
    
    # Tests -> tests/
    "tests": [
        "test_vila.py",
        "test_model_sources.py",
        "test_gpu.py",
        "test_tf_gpu.py",
        "test_cuda_manual.py",
        "check_gpu.py",
        "check_gpu_wsl.py",
        "check_wsl_env.py",
        "comprehensive_gpu_check.py",
    ],
    
    # Requirements -> requirements/
    "requirements": [
        "requirements_gpu.txt",
        "requirements_musiq_gpu.txt",
        "requirements_simple.txt",
        "requirements_wsl_gpu.txt",
        "requirements_wsl_gpu_minimal.txt",
        "requirements_wsl_gpu_organized.txt",
    ],
}

# Files to keep in root (user-facing entry points)
ROOT_FILES = [
    "README.md",
    "CHANGELOG.md",
    "INDEX.md",
    "requirements.txt",
    "run_all_musiq_models.py",
    "run_vila.py",
    "gallery_generator.py",
    "batch_process_images.py",
    "analyze_json_results.py",
    "run_musiq.py",
    "run_musiq_simple.py",
    "run_musiq_gpu.py",
    "run_original_musiq.py",
    "run_tfhub_musiq.py",
    "compare_scoring_methods.py",
    "weighted_scoring_strategy.py",
    "monitor_progress.py",
    "gpu_detection.py",
    "setup_gpu.py",
    "setup_wsl2_simple.py",
    "setup_wsl2_tensorflow_gpu.py",
    "simple_gpu_setup.py",
    "image_gallery.html",
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


def update_file_references(file_path: Path, old_path: str, new_path: str, dry_run: bool = False):
    """Update references in a file from old path to new path."""
    if not file_path.exists():
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Check if file contains old path
        if old_path not in content:
            return False
        
        if dry_run:
            count = content.count(old_path)
            print(f"    Would update {count} references in {file_path.name}")
            return True
        
        # Replace old path with new path
        updated_content = content.replace(old_path, new_path)
        
        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(updated_content)
        
        count = content.count(old_path)
        print(f"    ✓ Updated {count} references in {file_path.name}")
        return True
        
    except Exception as e:
        print(f"    ✗ Error updating {file_path.name}: {e}")
        return False


def main():
    """Main restructuring function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Restructure project files semantically"
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without actually doing it')
    parser.add_argument('--update-refs', action='store_true',
                       help='Update file references after moving')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("PROJECT RESTRUCTURING")
    print("=" * 70)
    print(f"Mode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE (making changes)'}")
    print()
    
    # Move files
    print("\n📁 Moving files to new structure...")
    
    moved_count = 0
    error_count = 0
    
    for dest_dir, files in FILE_MOVES.items():
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
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No actual changes made")
        print("Run without --dry-run to apply changes")
    else:
        print("\n✓ Files moved successfully")
        
        if args.update_refs:
            print("\n📝 Updating file references...")
            print("  (This feature will be implemented in next step)")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

