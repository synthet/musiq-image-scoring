# Project Restructure Plan

## Proposed Folder Structure

```
image-scoring/
├── README.md                    # Main readme (root)
├── CHANGELOG.md                 # Changelog (root)
├── INDEX.md                     # Documentation index (root)
├── requirements.txt             # Main requirements (root)
│
├── docs/                        # 📚 All documentation
│   ├── README.md                # Docs overview
│   ├── getting-started/         # Quick start guides
│   │   ├── README.md
│   │   ├── README_simple.md
│   │   ├── VERSION_2.3.0_RELEASE_NOTES.md
│   │   └── COMPLETE_SESSION_SUMMARY.md
│   ├── vila/                    # VILA-specific documentation
│   │   ├── README_VILA.md
│   │   ├── VILA_QUICK_START.md
│   │   ├── VILA_BATCH_FILES_GUIDE.md
│   │   ├── VILA_INTEGRATION_SUMMARY.md
│   │   ├── VILA_ALL_FIXES_SUMMARY.md
│   │   ├── VILA_FIXES_SUMMARY.md
│   │   ├── VILA_COMPLETE_SUMMARY.md
│   │   ├── VILA_MODEL_PATH_FIX.md
│   │   ├── VILA_PARAMETER_FIX.md
│   │   └── VILA_SCORE_RANGE_CORRECTION.md
│   ├── gallery/                 # Gallery documentation
│   │   ├── GALLERY_GENERATOR_README.md
│   │   ├── GALLERY_README.md
│   │   ├── GALLERY_VILA_UPDATE.md
│   │   └── GALLERY_SORTING_FIX.md
│   ├── setup/                   # Setup and configuration
│   │   ├── WSL2_SETUP_COMPLETE.md
│   │   ├── WSL2_TENSORFLOW_GPU_SETUP.md
│   │   ├── WSL_WRAPPER_VERIFICATION.md
│   │   ├── WSL_PYTHON_ENVIRONMENT_STATUS.md
│   │   ├── WSL_PYTHON_PACKAGES.md
│   │   ├── WSL_UBUNTU_PACKAGES.md
│   │   ├── GPU_SETUP_STATUS.md
│   │   ├── GPU_IMPLEMENTATION_SUMMARY.md
│   │   ├── install_cuda.md
│   │   ├── README_gpu.md
│   │   └── WINDOWS_SCRIPTS_README.md
│   ├── technical/               # Technical summaries and analysis
│   │   ├── MODELS_SUMMARY.md
│   │   ├── MODEL_FALLBACK_MECHANISM.md
│   │   ├── TRIPLE_FALLBACK_SYSTEM.md
│   │   ├── MODEL_SOURCE_TESTING.md
│   │   ├── CHECKPOINT_STATUS.md
│   │   ├── WEIGHTED_SCORING_STRATEGY.md
│   │   ├── ANALYSIS_SCRIPT_DOCUMENTATION.md
│   │   ├── BATCH_PROCESSING_SUMMARY.md
│   │   ├── README_MULTI_MODEL.md
│   │   └── PROJECT_STRUCTURE_ANALYSIS.md
│   └── maintenance/             # Project maintenance docs
│       ├── CLEANUP_SUMMARY.md
│       ├── ENVIRONMENT_CLEANUP_SUMMARY.md
│       └── SESSION_UPDATE_SUMMARY.md
│
├── scripts/                     # 🔧 All executable scripts
│   ├── batch/                   # Windows batch files
│   │   ├── create_gallery.bat
│   │   ├── create_gallery_simple.bat
│   │   ├── process_images.bat
│   │   ├── batch_process_images.bat
│   │   ├── open_gallery.bat
│   │   ├── open_historical_gallery.bat
│   │   ├── open_today_gallery.bat
│   │   ├── run_musiq_advanced.bat
│   │   ├── run_musiq_drag_drop.bat
│   │   ├── run_musiq_gpu.bat
│   │   ├── run_all_musiq_models_drag_drop.bat
│   │   ├── run_vila.bat
│   │   ├── run_vila_drag_drop.bat
│   │   ├── test_vila.bat
│   │   ├── test_model_sources.bat
│   │   └── analyze_results.bat
│   ├── powershell/              # PowerShell scripts
│   │   ├── Create-Gallery.ps1
│   │   ├── Process-Images.ps1
│   │   ├── Batch-Process-Images.ps1
│   │   ├── Open-Gallery.ps1
│   │   ├── Open-Historical-Gallery.ps1
│   │   ├── Open-Today-Gallery.ps1
│   │   ├── Run-All-MUSIQ-Models.ps1
│   │   ├── Run-MUSIQ-GPU.ps1
│   │   ├── Analyze-Results.ps1
│   │   └── Test-ModelSources.ps1
│   └── python/                  # Main Python entry points (keep in root for easy access)
│       # These will have symlinks in root for backward compatibility
│
├── src/                         # 💻 Source code (libraries)
│   ├── models/                  # Model loading and inference
│   │   ├── __init__.py
│   │   ├── multi_model_musiq.py  # From run_all_musiq_models.py
│   │   └── vila_scorer.py        # From run_vila.py
│   ├── gallery/                 # Gallery generation
│   │   ├── __init__.py
│   │   └── generator.py          # From gallery_generator.py
│   ├── batch/                   # Batch processing
│   │   ├── __init__.py
│   │   └── processor.py          # From batch_process_images.py
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── gpu_utils.py
│       └── path_utils.py
│
├── tests/                       # 🧪 Test scripts
│   ├── test_vila.py
│   ├── test_model_sources.py
│   ├── test_gpu.py
│   ├── test_tf_gpu.py
│   ├── test_cuda_manual.py
│   └── check_*.py files
│
├── requirements/                # 📦 Requirements files
│   ├── base.txt                 # requirements.txt
│   ├── gpu.txt                  # requirements_gpu.txt
│   ├── wsl_gpu.txt              # requirements_wsl_gpu.txt
│   └── [other requirements]
│
├── output/                      # 🎨 Generated files
│   └── .gitkeep
│
├── musiq_original/              # Original MUSIQ (preserve as-is)
│   └── [existing structure]
│
└── .archive/                    # 🗄️ Old/deprecated files
    └── [deprecated scripts]
```

## File Mappings

### Keep in Root (User-facing)
- README.md
- CHANGELOG.md
- INDEX.md
- requirements.txt
- run_all_musiq_models.py (main entry point)
- run_vila.py (main entry point)
- gallery_generator.py (main entry point)
- batch_process_images.py (main entry point)

### Move to docs/
All .md files except root ones

### Move to scripts/
All .bat and .ps1 files

### Move to tests/
All test_*.py and check_*.py files

### Move to requirements/
All requirements*.txt files (except main one)

