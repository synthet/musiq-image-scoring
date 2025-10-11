#!/usr/bin/env python3
"""
Update All References After Restructuring

This script updates all file references in documentation and scripts
after moving files to new locations.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

# File movement mappings (from restructure_project.py)
PATH_MAPPINGS = {
    # Documentation
    "README_simple.md": "docs/getting-started/README_simple.md",
    "VERSION_2.3.0_RELEASE_NOTES.md": "docs/getting-started/VERSION_2.3.0_RELEASE_NOTES.md",
    "COMPLETE_SESSION_SUMMARY.md": "docs/getting-started/COMPLETE_SESSION_SUMMARY.md",
    
    # VILA docs
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
    
    # Batch scripts
    "create_gallery.bat": "scripts/batch/create_gallery.bat",
    "test_vila.bat": "scripts/batch/test_vila.bat",
    "test_model_sources.bat": "scripts/batch/test_model_sources.bat",
    
    # PowerShell scripts
    "Create-Gallery.ps1": "scripts/powershell/Create-Gallery.ps1",
    "Test-ModelSources.ps1": "scripts/powershell/Test-ModelSources.ps1",
    
    # Python tests
    "test_vila.py": "tests/test_vila.py",
    "test_model_sources.py": "tests/test_model_sources.py",
}


def update_markdown_links(content: str, mappings: Dict[str, str]) -> str:
    """Update markdown links to reflect new paths."""
    for old_path, new_path in mappings.items():
        # Match markdown links: [text](old_path)
        patterns = [
            f"\\[([^\\]]+)\\]\\({old_path}\\)",  # [text](file.md)
            f"\\[([^\\]]+)\\]\\({re.escape(old_path)}\\)",  # With special chars
        ]
        
        for pattern in patterns:
            content = re.sub(pattern, f"[\\1]({new_path})", content)
    
    return content


def main():
    print("This would update all references after restructuring")
    print("Run after restructure_project.py completes")


if __name__ == "__main__":
    main()

