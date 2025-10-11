#!/usr/bin/env python3
"""
Update Script Paths After Phase 2 Restructuring

Updates batch and PowerShell scripts to reference Python scripts in their new locations.
"""

import re
from pathlib import Path

# Python script relocations
PYTHON_RELOCATIONS = {
    "run_vila.py": "scripts/python/run_vila.py",
    "gallery_generator.py": "scripts/python/gallery_generator.py",
    "batch_process_images.py": "scripts/python/batch_process_images.py",
    "run_musiq.py": "scripts/python/run_musiq.py",
    "run_musiq_simple.py": "scripts/python/run_musiq_simple.py",
    "run_musiq_gpu.py": "scripts/python/run_musiq_gpu.py",
    "run_tfhub_musiq.py": "scripts/python/run_tfhub_musiq.py",
    "run_original_musiq.py": "scripts/python/run_original_musiq.py",
    "analyze_json_results.py": "scripts/analysis/analyze_json_results.py",
    "test_vila.py": "tests/test_vila.py",
    "test_model_sources.py": "tests/test_model_sources.py",
}


def update_batch_file(file_path: Path, dry_run: bool = False):
    """Update Python script references in batch files."""
    if not file_path.exists():
        return False, 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        original_content = content
        updates = 0
        
        for old_path, new_path in PYTHON_RELOCATIONS.items():
            # Patterns in batch files
            patterns = [
                # python script.py
                (f'python "{old_path}"', f'python "%~dp0..\\..\\{new_path.replace("/", chr(92))}"'),
                (f'python {old_path}', f'python "%~dp0..\\..\\{new_path.replace("/", chr(92))}"'),
                (f'python "%SCRIPT_DIR%{old_path}"', f'python "%~dp0..\\..\\{new_path.replace("/", chr(92))}"'),
                # WSL paths
                (f'&& python {old_path}', f'&& python {new_path}'),
            ]
            
            for pattern, replacement in patterns:
                if pattern in content:
                    content = content.replace(pattern, replacement)
                    updates += 1
        
        if updates == 0:
            return True, 0
        
        if dry_run:
            print(f"  Would update {updates} paths in {file_path.name}")
            return True, updates
        
        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(content)
        
        print(f"  ✓ Updated {updates} paths in {file_path.name}")
        return True, updates
        
    except Exception as e:
        print(f"  ✗ Error updating {file_path.name}: {e}")
        return False, 0


def update_powershell_file(file_path: Path, dry_run: bool = False):
    """Update Python script references in PowerShell files."""
    if not file_path.exists():
        return False, 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        original_content = content
        updates = 0
        
        for old_path, new_path in PYTHON_RELOCATIONS.items():
            # PowerShell patterns
            patterns = [
                (f'python "{old_path}"', f'python "$PSScriptRoot\\..\\..\\{new_path.replace("/", chr(92))}"'),
                (f'python "$ScriptDir\\{old_path}"', f'python "$PSScriptRoot\\..\\..\\{new_path.replace("/", chr(92))}"'),
                # WSL paths
                (f'&& python {old_path}', f'&& python {new_path}'),
            ]
            
            for pattern, replacement in patterns:
                if pattern in content:
                    content = content.replace(pattern, replacement)
                    updates += 1
        
        if updates == 0:
            return True, 0
        
        if dry_run:
            print(f"  Would update {updates} paths in {file_path.name}")
            return True, updates
        
        with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(content)
        
        print(f"  ✓ Updated {updates} paths in {file_path.name}")
        return True, updates
        
    except Exception as e:
        print(f"  ✗ Error updating {file_path.name}: {e}")
        return False, 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Update script paths after Phase 2")
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    
    print("=" * 70)
    print("UPDATING SCRIPT PATHS (Phase 2)")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    total_files = 0
    total_updates = 0
    
    # Update batch files
    print("\n📝 Updating batch files...")
    for bat_file in Path("scripts/batch").glob("*.bat"):
        success, count = update_batch_file(bat_file, args.dry_run)
        if count > 0:
            total_files += 1
            total_updates += count
    
    # Update PowerShell files
    print("\n📝 Updating PowerShell files...")
    for ps1_file in Path("scripts/powershell").glob("*.ps1"):
        success, count = update_powershell_file(ps1_file, args.dry_run)
        if count > 0:
            total_files += 1
            total_updates += count
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files updated: {total_files}")
    print(f"Total path updates: {total_updates}")
    
    if not args.dry_run:
        print("\n✓ Script paths updated successfully")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

