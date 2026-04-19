# MUSIQ Image Scoring - Digital Asset Management System

A comprehensive **AI-powered Digital Asset Management** tool for photographers and creative professionals, featuring:

- 🎯 **Multi-Model Quality Scoring**: Technical and aesthetic assessment using Google's MUSIQ, LIQE, and other SOTA models
- 🖼️ **Interactive Web Gallery**: Gradio-based UI for browsing, filtering, and managing your image library
- 💻 **Standalone Desktop App**: High-performance **[Electron Gallery](https://github.com/synthet/image-scoring-gallery)** for native-feeling browsing
- 🏷️ **AI Keyword Extraction**: Automatic tagging using BLIP + CLIP vision-language models
- 📸 **RAW File Support**: Native support for Nikon NEF (Z8/Z9 HE*), Canon CR2, Sony ARW, and other RAW formats
- ⚡ **GPU Acceleration**: CUDA support for 10-15x faster batch processing
- 🐳 **Multiple Deployment Options**: Docker, WSL2, or native Windows

**📚 [Complete Documentation Index](docs/README.md)** | **🚀 [Quick Reference](docs/gallery/QUICK_REFERENCE.md)** | **📊 [Test Status](docs/testing/TEST_STATUS.md)**

## Quick Setup

Copy `config.example.json` to `config.json` (gitignored). Optionally copy `environment.example.json` to `environment.json` for machine-specific paths, ports, and URLs; `environment.json` overrides overlapping keys in `config.json`.

Choose your deployment method based on your needs:

| Method | Best For | GPU Support | Setup Time | Complexity |
|--------|----------|-------------|------------|------------|
| **🐳 Docker** | Quick start, production | ✅ Yes (via WSL2) | 5 min | ⭐ Easy |
| **🐧 WSL2** | Development, full control | ✅ Yes (native CUDA) | 15 min | ⭐⭐ Moderate |
| **🪟 Windows** | Simple CLI tasks | ❌ CPU only | 5 min | ⭐ Easy |

### Option 1: Docker (Recommended for Most Users)

**Why Docker?** Fastest setup with full GPU support, no manual dependency management, and consistent environment.

**Prerequisites:**
- Windows 10/11 with WSL2 enabled
- Docker Desktop installed ([Download here](https://www.docker.com/products/docker-desktop/))
- NVIDIA GPU drivers (for GPU acceleration)

**Setup:**

1. **Install Docker Desktop** and ensure WSL2 backend is enabled in settings

2. **Launch the WebUI:**
   ```cmd
   run_webui_docker.bat
   ```

3. **Access the interface** at `http://localhost:7860`

That's it! The Docker container includes all dependencies, CUDA support, and connects to your Windows Firebird database automatically.

📖 **See also:** [Docker Deployment Guide](docs/setup/WINDOWS_WSL_DEPLOYMENT.md#docker-option)

---

### Option 2: WSL2 (Recommended for Development)

**Why WSL?** Best for active development, debugging, and maximum performance. Full access to Linux tools and native CUDA.

**Prerequisites:**
- Windows 10 (Build 19044+) or Windows 11
- NVIDIA GPU with updated drivers

**Setup:**

1. **Install WSL2** (if not already installed):
   ```powershell
   # In PowerShell as Administrator
   wsl --install
   # Restart your computer
   ```

2. **Set up Python environment in WSL**:
   ```cmd
   setup.bat
   ```
   Or manually in WSL:
   ```bash
   mkdir -p ~/.venvs
   python3 -m venv ~/.venvs/tf
   source ~/.venvs/tf/bin/activate
   cd /path/to/image-scoring
   pip install --upgrade pip
   pip install -r requirements/requirements_wsl_gpu.txt  # Canonical WSL/Linux GPU requirements
   ```

3. **Verify GPU access**:
   ```bash
   python -c "import tensorflow as tf; print('GPUs:', len(tf.config.list_physical_devices('GPU')))"
   ```

4. **Launch WebUI**:
   ```bash
   python launch.py
   ```

📖 **Detailed guide:** [WSL2 TensorFlow GPU Setup](docs/setup/WSL2_TENSORFLOW_GPU_SETUP.md) | [Windows/WSL Deployment](docs/setup/WINDOWS_WSL_DEPLOYMENT.md) | [Python & Dependency Version Caveats](docs/setup/PYTHON_VERSION_CAVEATS.md)

---

### Option 3: Windows Native (Limited Support)

**Why Windows?** Simple setup for basic CLI scoring tasks. **Note:** No VILA model support, CPU-only processing (slower).

**Setup:**

```bash
# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Command Prompt)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt  # Canonical Windows-native requirements
```

**Limitations:**
- ❌ No VILA model (requires TensorFlow Hub + Kaggle)
- ❌ No GPU acceleration in this Windows-native path (use Docker/WSL2 GPU requirements instead)
- ⚠️ Slower batch processing (5-10x slower than GPU)

📖 **For production use, we strongly recommend Docker or WSL2.**

📖 **Version caveats:** [Python & Dependency Version Caveats](docs/setup/PYTHON_VERSION_CAVEATS.md)

---

### Option 3b: Windows Native WebUI

**Why?** Run the Gradio WebUI natively on Windows without WSL. CPU-only, no VILA.

**Prerequisites:** Compatible Python (see [Python & Dependency Version Caveats](docs/setup/PYTHON_VERSION_CAVEATS.md)), Firebird binaries in `Firebird/` (firebird.exe, fbclient.dll — see [Firebird 5.0](https://firebirdsql.org/en/firebird-5-0/) Embedded package).

**Setup:**

```batch
scripts\setup\setup_windows_native.bat
```

**Launch:**

```batch
run_webui_windows.bat
```

**Limitations:**
- CPU-only TensorFlow (no GPU)
- No VILA model
- Slower than WSL2/Docker with GPU

---

### Quick Test

After setup, verify your installation:

```bash
# Docker
docker exec -it image-scoring-webui python -c "import tensorflow as tf; print('Setup OK!')"

# WSL2
python -c "import tensorflow as tf; print('Setup OK!')"

# Windows
python -c "import tensorflow as tf; print('Setup OK!')"
```

## Usage

### Web Interface (Recommended)

The **Gradio WebUI** is the primary interface for most users, providing an intuitive dashboard for scoring, browsing, and managing your image library.

**Launch WebUI:**

```bash
# Docker
run_webui_docker.bat

# WSL2
run_webui.bat
# Or directly: python launch.py

# Windows
python launch.py
```

**Access:** Open `http://localhost:7860` in your browser

**Features:**
- 📊 **Dashboard**: Visual score breakdowns with model-specific metrics
- 🖼️ **Gallery**: Browse and filter images by score, date, rating, or keywords
- ✏️ **Metadata Editor**: Edit titles, descriptions, keywords, ratings, and color labels
- 🎯 **Smart Filters**: Filter by score ranges (e.g., Aesthetic > 0.7) and date
- 📤 **Export**: Curate and export your best shots
- 💾 **Persistence**: Settings remembered between sessions

📖 **See:** [WebUI Workflow](/.agent/workflows/run_webui.md) | [Gallery Guide](docs/gallery/GALLERY_GENERATOR_README.md)

---

### Command Line Interface

For batch processing and automation, use the CLI tools:

#### Score Images

```bash
# Score a single image
python scripts/python/run_all_musiq_models.py --image sample.jpg

# Score an entire folder
python scripts/python/run_all_musiq_models.py --input-dir "D:/Photos/Portfolio"

# Use workflow for full pipeline
# See: .agent/workflows/run_scoring.md
```

#### Extract Keywords

```bash
# Process a folder of images
python scripts/python/keyword_extractor.py --input-dir "D:/Photos/NEF_Files"

# Process with custom confidence threshold
python scripts/python/keyword_extractor.py --input-dir "D:/Photos" --confidence-threshold 0.05

# Windows batch script
extract_keywords.bat "D:\Photos\NEF_Files"
```

📖 **See:** [Scoring Guide](docs/getting-started/SCORING_GUIDE.md) | [Keyword Extraction Guide](docs/technical/KEYWORD_EXTRACTION_GUIDE.md)

---

## Features

### 🎯 Multi-Model Quality Assessment

Hybrid scoring system combining technical and aesthetic evaluation:

- **MUSIQ Models** (Technical - 75%): KONIQ, SPAQ, PAQ2PIQ, AVA
- **LIQE Model** (Aesthetic - 15%): State-of-the-art vision-language quality evaluator
- **VILA Model** (Optional): Advanced aesthetic scoring (WSL2/Docker only)

**Score Weights (v2.5.2):**

| Model | Weight | Role |
|-------|--------|------|
| **KONIQ** | 30% | Technical Reliability |
| **SPAQ** | 25% | Technical Discrimination |
| **PAQ2PIQ** | 20% | Artifacts/Detail |
| **LIQE** | **15%** | **SOTA Aesthetic/Semantic** |
| **AVA** | 10% | Legacy Aesthetic |

📖 **See:** [Weighted Scoring Strategy](docs/technical/WEIGHTED_SCORING_STRATEGY.md) | [Models Summary](docs/technical/MODELS_SUMMARY.md)

### 🖼️ Interactive Web Gallery

- **Visual Dashboard**: Deep-dive analysis with score bars and model breakdowns
- **Smart Filtering**: By score ranges, dates, ratings, and keywords
- **Metadata Management**: Edit titles, descriptions, keywords inline
- **Export Workflow**: Curate and export your best images
- **Responsive Design**: Works on desktop and tablet

### 🏷️ AI Keyword Extraction

- **BLIP + CLIP Pipeline**: State-of-the-art vision-language models
- **Automatic Captioning**: Natural language descriptions
- **Confidence Scoring**: Each keyword includes confidence metrics
- **Domain-Aware**: Photography-specific keyword enhancement
- **Batch Processing**: Process entire folders efficiently

### 📸 RAW File Support

- **Nikon**: NEF (including Z8/Z9 HE* high-efficiency formats)
- **Canon**: CR2, CR3
- **Sony**: ARW
- **Others**: DNG, ORF, RAF, and more via ExifTool + rawpy

### ⚡ Performance

- **GPU Acceleration**: 10-15x faster with CUDA (WSL2/Docker)
- **Batch Processing**: Efficient multi-threaded pipeline
- **Smart Caching**: Avoid re-processing scored images
- **Database**: Firebird SQL for fast queries and metadata storage

## Output Format

### Image Quality Scoring

The tool outputs two lines:
1. Human-readable score: `MUSIQ score: 6.87`
2. JSON format: `{"path": "sample.jpg", "score": 6.87, "model": "spaq"}`

### AI Keyword Extraction

Each processed image generates a JSON file with:

```json
{
  "image_path": "D:/Photos/image.nef",
  "caption": "a bird standing on a rock near water",
  "keywords": [
    {"keyword": "bird", "confidence": 0.85, "source": "clip"},
    {"keyword": "water", "confidence": 0.72, "source": "clip"},
    {"keyword": "nature", "confidence": 0.68, "source": "clip"}
  ],
  "total_keywords_found": 45,
  "keywords_above_threshold": 12,
  "confidence_threshold": 0.03,
  "device": "cuda",
  "timestamp": "2024-01-15T10:30:00"
}
```

## Available Models

This project uses a **Hybrid Scoring System** combining multiple state-of-the-art models:

### MUSIQ Models (Technical Foundation - 75%)
Based on Google's Multi-scale Image Quality Transformer:
- **KONIQ** (30%): Primary technical reference (Reliability)
- **SPAQ** (25%): Secondary technical reference (Discrimination)
- **PAQ2PIQ** (20%): Detail and artifact detection
- **AVA** (10%): Legacy aesthetic input

### LIQE Model (Aesthetic & Semantic - 15%)
**Language-Image Quality Evaluator**: State-of-the-art model using CLIP technology to understand image content and aesthetics.
- Requires PyTorch environment
- Automatically runs as a sub-process

### VILA Model (Optional)
**Vision-Language Aesthetic Scorer**: Advanced aesthetic evaluation using vision-language models.
- ✅ **Available in WSL2/Docker** with full TensorFlow Hub + Kaggle support
- ❌ **Not available in Windows native** due to TensorFlow/Kaggle Hub limitations
- Provides additional aesthetic insights when enabled

📖 **See:** [Models Summary](docs/technical/MODELS_SUMMARY.md) | [Weighted Scoring Strategy](docs/technical/WEIGHTED_SCORING_STRATEGY.md)

## Model Loading & Reliability

The tool uses a **triple fallback mechanism** for maximum reliability:

1. **TensorFlow Hub** (Primary) - Fast, no authentication required
2. **Kaggle Hub** (Fallback) - Requires `kaggle.json` authentication
3. **Local Checkpoints** (Offline) - Uses cached `.npz` or SavedModel files

**Reliability**: 99.9%+ uptime with automatic fallback between sources.

📖 **See:** [Triple Fallback System](docs/archive/TRIPLE_FALLBACK_SYSTEM.md) | [Model Source Testing](docs/technical/MODEL_SOURCE_TESTING.md)

---

## Troubleshooting

### Docker Issues

1. **"Docker is not running"**:
   - Start Docker Desktop
   - Ensure WSL2 backend is enabled in Docker Desktop settings

2. **GPU not detected in container**:
   - Verify NVIDIA drivers are installed on Windows
   - Check Docker Desktop has GPU support enabled
   - Run: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi`

3. **Database connection errors**:
   - Ensure Firebird service is running on Windows
   - Check Windows Firewall allows port 3050

### WSL2 Issues

1. **"nvidia-smi not found"**:
   - Update NVIDIA drivers on Windows (not in WSL)
   - Restart WSL: `wsl --shutdown` then reopen

2. **TensorFlow GPU not detected**:
   ```bash
   pip uninstall tensorflow
   pip install -r requirements/requirements_wsl_gpu.txt
   ```

3. **Import errors**:
   ```bash
   sudo apt install libgl1 libsm6 libxext6
   pip install --upgrade pip
   pip install -r requirements/requirements_wsl_gpu.txt  # Reinstall canonical WSL/Linux GPU requirements
   ```

### Windows Native Issues

1. **Model download failures**:
   - Check internet connection
   - Verify TensorFlow Hub access
   - Try different model variant

2. **Memory issues**:
   - Use smaller images
   - Close other applications
   - Consider using Docker or WSL2 instead

### General Issues

- **Slow processing**: Use Docker or WSL2 with GPU acceleration
- **Database locked**: Ensure only one instance is running
- **Missing scores**: Check logs in WebUI or `logs/` directory

### Git / Merge Issues

1. **`git pull` reports conflicts (e.g., `modules/api.py`, `modules/db.py`)**:
   ```bash
   # 1) Confirm conflicted files
   git status

   # 2) Open each conflicted file and resolve blocks between:
   # <<<<<<< HEAD
   # =======
   # >>>>>>> <incoming-branch>

   # 3) Mark each file as resolved
   git add modules/api.py modules/db.py modules/metadata_runner.py

   # 4) Complete the merge
   git commit
   ```
   - In VS Code, you can use **Accept Current / Accept Incoming / Accept Both** for each hunk.
   - Re-run `git status` after editing; it should no longer show **unmerged paths**.
   - If you want to discard the merge attempt and start over: `git merge --abort`.
   - Before pushing, validate with `git pull --rebase` (or your team’s preferred pull strategy) to reduce future conflicts.

📖 **See also:** [Project Review](docs/reports/project-reviews/PROJECT_REVIEW_DETAILED_2026-01-31.md) | [Test Status](docs/testing/TEST_STATUS.md)

---

## Features

### Image Quality Scoring
- **MUSIQ Models**: SPAQ, AVA, KONIQ, PAQ2PIQ quality assessment
- **VILA Integration**: Advanced aesthetic scoring (WSL recommended)
- **Batch Processing**: Process entire folders of images
- **NEF Support**: Full Nikon Raw file support

### Web Interface (v2.0 - Digital Asset Management)
- **Visual Dashboard**: Deep-dive analysis with score bars and model breakdowns
- **Interactive Metadata Editor**: Edit Title, Description, Keywords, Rating, and Color Label directly
- **Smart Filters**: Filter by Score Ranges (e.g., Aesthetic > 0.7) and Date
- **Export Workflow**: Curate and export your best shots
- **Persistence**: Remembers your settings between sessions

### AI Keyword Extraction
- **BLIP + CLIP Pipeline**: State-of-the-art AI models for keyword extraction
- **Automatic Captioning**: Generate natural language descriptions
- **Confidence Scoring**: Each keyword comes with confidence scores
- **Domain-Aware**: Photography-specific keyword enhancement
- **Batch Processing**: Extract keywords from entire folders

## Dependencies

Dependency versions are maintained in platform-specific requirements files.

- **WSL2 / Linux GPU (recommended):** [`requirements/requirements_wsl_gpu.txt`](requirements/requirements_wsl_gpu.txt)
- **Windows-native CPU workflow:** [`requirements.txt`](requirements.txt)
- **Minimal CPU experiments:** [`requirements/requirements_simple.txt`](requirements/requirements_simple.txt)

📖 **Version caveats and platform guidance:** [Python & Dependency Version Caveats](docs/setup/PYTHON_VERSION_CAVEATS.md)

---

## Getting Help

### Quick Decision Tree

**I want to...**

- **Get started quickly** → Use [Docker setup](#option-1-docker-recommended-for-most-users)
- **Score a folder of images** → See [WebUI Usage](#web-interface-recommended) or [run_scoring workflow](/.agent/workflows/run_scoring.md)
- **View and manage my scored images** → Launch the [WebUI](#web-interface-recommended)
- **Extract keywords from images** → See [Keyword Extraction](#extract-keywords)
- **Understand the scoring system** → Read [Weighted Scoring Strategy](docs/technical/WEIGHTED_SCORING_STRATEGY.md)
- **Set up for development** → Use [WSL2 setup](#option-2-wsl2-recommended-for-development)
- **Troubleshoot an issue** → Check [Troubleshooting](#troubleshooting) or [Project Review](docs/technical/PROJECT_REVIEW_DETAILED_2026-01-31.md)
- **Learn about the architecture** → Read [Technical Summary](docs/technical/technical_summary.md)
- **See what's new** → Check [CHANGELOG.md](CHANGELOG.md)

### Documentation Index

📚 **[Complete Documentation Index](docs/README.md)** - Comprehensive guide to all documentation

**Key Documents:**
- [Quick Reference](docs/getting-started/QUICK_REFERENCE.md) - Command cheat sheet
- [Scoring Guide](docs/getting-started/SCORING_GUIDE.md) - Detailed scoring guide
- [WSL2 Setup Guide](docs/setup/WSL2_TENSORFLOW_GPU_SETUP.md) - GPU setup in WSL2
- [Windows/WSL Deployment](docs/setup/WINDOWS_WSL_DEPLOYMENT.md) - Full deployment guide
- [Gallery Creation](docs/gallery/GALLERY_CREATION.md) - Gallery creation guide
   - [Keyword Extraction](docs/technical/KEYWORD_EXTRACTION_GUIDE.md) - AI keyword extraction
- [Triple Fallback System](docs/archive/TRIPLE_FALLBACK_SYSTEM.md) - Model loading reliability
- [MCP Debugging Tools](docs/technical/MCP_DEBUGGING_TOOLS.md) - Advanced debugging
- [Architecture Documentation](docs/technical/ARCHITECTURE.md) - System overview and design


---

## Implementation Notes

This tool uses a simplified approach for CPU-only inference:
- Avoids heavy JAX/Flax dependencies from original implementation
- Uses TensorFlow Hub for stable model loading
- Handles multi-scale image processing automatically
- Provides fallback to local checkpoints if available

---

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997) - Original MUSIQ research
- [VILA Paper](https://arxiv.org/abs/2312.07533) - VILA vision-language model
- [Google Research Repository](https://github.com/google-research/google-research/tree/master/musiq) - MUSIQ code
- [TensorFlow Hub Models](https://tfhub.dev/s?q=musiq) - TF Hub model collection
- [Kaggle Hub VILA](https://www.kaggle.com/models/google/vila) - VILA on Kaggle

---

**License**: This implementation is for educational and demonstration purposes. The original MUSIQ research is from Google Research.
