#!/usr/bin/env python3
"""
Update All File References After Restructuring

Updates all links and references in documentation and scripts
to reflect the new folder structure.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Path mappings for documentation files
DOC_MAPPINGS = {
    # Getting started
    "README_simple.md": "docs/getting-started/README_simple.md",
    "VERSION_2.3.0_RELEASE_NOTES.md": "docs/getting-started/VERSION_2.3.0_RELEASE_NOTES.md",
    "COMPLETE_SESSION_SUMMARY.md": "docs/getting-started/COMPLETE_SESSION_SUMMARY.md",
    
    # VILA docs (10 files)
    "README_VILA.md": "docs/vila/README_VILA.md",
    "VILA_QUICK_START.md": "docs/vila/VILA_QUICK_START.md",
    "VILA_BATCH_FILES_GUIDE.md": "docs/vila/VILA_BATCH_FILES_GUIDE.md",
    "VILA_INTEGRATION_SUMMARY.md": "docs/vila/VILA_INTEGRATION_SUMMARY.md",
    "VILA_ALL_FIXES_SUMMARY.md": "docs/vila/VILA_ALL_FIXES_SUMMARY.md",
    "VILA_FIXES_SUMMARY.md": "docs/vila/VILA_FIXES_SUMMARY.md",
    "VILA_COMPLETE_SUMMARY.md": "docs/vila/VILA_COMPLETE_SUMMARY.md",
    "VILA_MODEL_PATH_FIX.md": "docs/vila/VILA_MODEL_PATH_FIX.md",
    "VILA_PARAMETER_FIX.md": "docs/vila/VILA_PARAMETER_FIX.md",
    "VILA_SCORE_RANGE_CORRECTION.md": "docs/vila/VILA_SCORE_RANGE_CORRECTION.md",
    
    # Gallery docs
    "GALLERY_GENERATOR_README.md": "docs/gallery/GALLERY_GENERATOR_README.md",
    "GALLERY_README.md": "docs/gallery/GALLERY_README.md",
    "GALLERY_VILA_UPDATE.md": "docs/gallery/GALLERY_VILA_UPDATE.md",
    "GALLERY_SORTING_FIX.md": "docs/gallery/GALLERY_SORTING_FIX.md",
    
    # Setup docs
    "WSL2_SETUP_COMPLETE.md": "docs/setup/WSL2_SETUP_COMPLETE.md",
    "WSL2_TENSORFLOW_GPU_SETUP.md": "docs/setup/WSL2_TENSORFLOW_GPU_SETUP.md",
    "WSL_WRAPPER_VERIFICATION.md": "docs/setup/WSL_WRAPPER_VERIFICATION.md",
    "WSL_PYTHON_ENVIRONMENT_STATUS.md": "docs/setup/WSL_PYTHON_ENVIRONMENT_STATUS.md",
    "WSL_PYTHON_PACKAGES.md": "docs/setup/WSL_PYTHON_PACKAGES.md",
    "WSL_UBUNTU_PACKAGES.md": "docs/setup/WSL_UBUNTU_PACKAGES.md",
    "GPU_SETUP_STATUS.md": "docs/setup/GPU_SETUP_STATUS.md",
    "GPU_IMPLEMENTATION_SUMMARY.md": "docs/setup/GPU_IMPLEMENTATION_SUMMARY.md",
    "install_cuda.md": "docs/setup/install_cuda.md",
    "README_gpu.md": "docs/setup/README_gpu.md",
    "WINDOWS_SCRIPTS_README.md": "docs/setup/WINDOWS_SCRIPTS_README.md",
    
    # Technical docs
    "MODELS_SUMMARY.md": "docs/technical/MODELS_SUMMARY.md",
    "MODEL_FALLBACK_MECHANISM.md": "docs/technical/MODEL_FALLBACK_MECHANISM.md",
    "TRIPLE_FALLBACK_SYSTEM.md": "docs/technical/TRIPLE_FALLBACK_SYSTEM.md",
    "MODEL_SOURCE_TESTING.md": "docs/technical/MODEL_SOURCE_TESTING.md",
    "CHECKPOINT_STATUS.md": "docs/technical/CHECKPOINT_STATUS.md",
    "WEIGHTED_SCORING_STRATEGY.md": "docs/technical/WEIGHTED_SCORING_STRATEGY.md",
    "ANALYSIS_SCRIPT_DOCUMENTATION.md": "docs/technical/ANALYSIS_SCRIPT_DOCUMENTATION.md",
    "BATCH_PROCESSING_SUMMARY.md": "docs/technical/BATCH_PROCESSING_SUMMARY.md",
    "README_MULTI_MODEL.md": "docs/technical/README_MULTI_MODEL.md",
    "PROJECT_STRUCTURE_ANALYSIS.md": "docs/technical/PROJECT_STRUCTURE_ANALYSIS.md",
    
    # Maintenance docs
    "CLEANUP_SUMMARY.md": "docs/maintenance/CLEANUP_SUMMARY.md",
    "ENVIRONMENT_CLEANUP_SUMMARY.md": "docs/maintenance/ENVIRONMENT_CLEANUP_SUMMARY.md",
    "SESSION_UPDATE_SUMMARY.md": "docs/maintenance/SESSION_UPDATE_SUMMARY.md",
}

# Path mappings for scripts
SCRIPT_MAPPINGS = {
    # Batch scripts
    "test_vila.bat": "scripts/batch/test_vila.bat",
    "test_model_sources.bat": "scripts/batch/test_model_sources.bat",
    # PowerShell scripts
    "Test-ModelSources.ps1": "scripts/powershell/Test-ModelSources.ps1",
}

# Test file mappings
TEST_MAPPINGS = {
    "test_vila.py": "tests/test_vila.py",
    "test_model_sources.py": "tests/test_model_sources.py",
}

# Combine all mappings
ALL_MAPPINGS = {**DOC_MAPPINGS, **SCRIPT_MAPPINGS, **TEST_MAPPINGS}


def update_file(file_path: Path, dry_run: bool = False) -> Tuple[bool, int]:
    """
    Update file references in a single file.
    
    Returns: (success, number_of_updates)
    """
    if not file_path.exists():
        return False, 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            original_content = f.read()
        
        updated_content = original_content
        total_replacements = 0
        
        # Update markdown links: [text](old_path)
        for old_path, new_path in ALL_MAPPINGS.items():
            # Match various link formats
            patterns = [
                (f"\\[([^\\]]+)\\]\\({re.escape(old_path)}\\)", f"[\\1]({new_path})"),
                (f"\\[([^\\]]+)\\]\\(\\./{re.escape(old_path)}\\)", f"[\\1]({new_path})"),
                (f"See {re.escape(old_path)}", f"See {new_path}"),
                (f"see {re.escape(old_path)}", f"see {new_path}"),
                (f"Check {re.escape(old_path)}", f"Check {new_path}"),
            ]
            
            for pattern, replacement in patterns:
                new_content, count = re.subn(pattern, replacement, updated_content)
                if count > 0:
                    updated_content = new_content
                    total_replacements += count
        
        if total_replacements == 0:
            return True, 0
        
        if dry_run:
            print(f"  Would update {total_replacements} references in {file_path.name}")
            return True, total_replacements
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(updated_content)
        
        print(f"  ✓ Updated {total_replacements} references in {file_path.name}")
        return True, total_replacements
        
    except Exception as e:
        print(f"  ✗ Error updating {file_path.name}: {e}")
        return False, 0


def update_all_files(dry_run: bool = False):
    """Update all files that might contain references."""
    print("📝 Updating file references...")
    print()
    
    # Files to update (in root and subdirs)
    files_to_update = [
        # Root files
        "README.md",
        "CHANGELOG.md",
        "INDEX.md",
        "RESTRUCTURE_PLAN.md",
        
        # All .md files in docs/
        *Path("docs").rglob("*.md"),
        
        # All Python files in root
        *Path(".").glob("*.py"),
        
        # All batch files in scripts/
        *Path("scripts").rglob("*.bat"),
        
        # All PowerShell files in scripts/
        *Path("scripts").rglob("*.ps1"),
        
        # All test files
        *Path("tests").rglob("*.py"),
    ]
    
    total_files = 0
    total_updates = 0
    
    for file_path in files_to_update:
        file_path = Path(file_path)
        if file_path.is_file():
            success, count = update_file(file_path, dry_run)
            if count > 0:
                total_files += 1
                total_updates += count
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files updated: {total_files}")
    print(f"Total replacements: {total_updates}")
    
    if dry_run:
        print("\n⚠️  DRY RUN - No changes made")
    else:
        print("\n✓ References updated successfully")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Update all file references after restructuring"
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without making changes')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("UPDATING FILE REFERENCES")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    update_all_files(dry_run=args.dry_run)
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

