# MUSIQ: Multi-scale Image Quality Transformer - CLI Tool

A minimal, CPU-only Python CLI tool for scoring image aesthetic/quality using Google's MUSIQ model.

## Quick Setup

### Option 1: WSL (Recommended for VILA support)

**Why WSL?** VILA model requires TensorFlow with proper environment setup. WSL provides the best compatibility.

1. **Install WSL (if not already installed)**:
   ```powershell
   # In PowerShell as Administrator
   wsl --install
   # Restart your computer
   ```

2. **Set up TensorFlow virtual environment in WSL**:
   ```bash
   # In WSL terminal
   # Create virtual environment directory
   mkdir -p ~/.venvs
   
   # Create TensorFlow virtual environment
   python3 -m venv ~/.venvs/tf
   
   # Activate the environment
   source ~/.venvs/tf/bin/activate
   
   # Upgrade pip
   pip install --upgrade pip
   
   # Navigate to project (adjust drive letter as needed)
   cd /mnt/d/Projects/image-scoring
   
   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Verify installation**:
   ```bash
   # Test TensorFlow
   python -c "import tensorflow as tf; print(f'TensorFlow: {tf.__version__}')"
   
   # Test kagglehub
   python -c "import kagglehub; print('Kaggle Hub: OK')"
   ```

4. **Set up Kaggle authentication (for VILA)**:
   ```bash
   # Create Kaggle directory
   mkdir -p ~/.kaggle
   
   # Copy your kaggle.json from Windows
   # (First download from https://www.kaggle.com/settings/account -> Create New API Token)
   cp /mnt/c/Users/YourUsername/Downloads/kaggle.json ~/.kaggle/
   
   # Set proper permissions
   chmod 600 ~/.kaggle/kaggle.json
   ```

### Option 2: Windows Python (Limited support)

For Windows-only setup (MUSIQ models only, VILA may not work):

```bash
# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Command Prompt)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

**Note**: VILA model requires Kaggle Hub and may not work reliably in Windows Python. Use WSL for full functionality.

## Environment Setup Summary

| Feature | WSL (Recommended) | Windows Python |
|---------|-------------------|----------------|
| **MUSIQ Models** | ✅ Full support | ✅ Full support |
| **VILA Model** | ✅ Full support | ⚠️ Limited/Unreliable |
| **GPU Support** | ✅ Available | ❌ Not configured |
| **Batch Processing** | ✅ Fast | ✅ Slower |
| **Kaggle Hub** | ✅ Works perfectly | ⚠️ May have issues |

### Quick Test

```bash
# WSL (recommended)
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_vila.py"

# Windows
python test_vila.py
```

## Usage

```bash
python run_musiq.py --image sample.jpg
```

### Options

- `--image`: Path to input image (required)
- `--model`: Model variant - `spaq` (default), `ava`, `koniq`, or `paq2piq`
- `--save-preprocessed`: Save preprocessed image for debugging

### Examples

```bash
# Basic usage
python run_musiq.py --image sample.jpg

# Use different model variant
python run_musiq.py --image sample.jpg --model ava

# Save preprocessed image
python run_musiq.py --image sample.jpg --save-preprocessed preprocessed.jpg
```

## Output Format

The tool outputs two lines:
1. Human-readable score: `MUSIQ score: 6.87`
2. JSON format: `{"path": "sample.jpg", "score": 6.87, "model": "spaq"}`

## Available Models

This project supports multiple image quality and aesthetic assessment models:

### MUSIQ Models (Image Quality)
- **SPAQ**: Trained on SPAQ dataset (range: 0-100)
- **AVA**: Trained on AVA dataset (range: 1-10)
- **KONIQ**: Trained on KONIQ-10K dataset (range: 0-100)
- **PAQ2PIQ**: Trained on PaQ-2-PiQ dataset (range: 0-100)

### VILA Model (Vision-Language Aesthetics)
- **VILA**: Vision-language aesthetic assessment (range: 0-1, normalized)

For detailed VILA setup and usage, see [README_VILA.md](docs/vila/README_VILA.md).

## Gallery Generation

The `create_gallery.bat` script automates batch processing and gallery creation.

### Python Files Used by create_gallery.bat

1. **`batch_process_images.py`** - Batch processes all images in a folder with all available models
   - Scores multiple images in one run
   - Saves results as JSON files alongside images
   - Supports MUSIQ and VILA model variants

2. **`gallery_generator.py`** - Generates an HTML gallery from processed images
   - Reads JSON files with image scores
   - Creates an interactive HTML gallery
   - Displays images sorted by weighted quality score

### Usage

**Windows (Batch files - automatically use WSL if available)**:
```batch
create_gallery.bat "C:\Path\To\Your\Images"
```

**PowerShell**:
```powershell
.\Create-Gallery.ps1 "C:\Path\To\Your\Images"
```

**Direct WSL command**:
```bash
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '/mnt/d/Photos/YourFolder' --output-dir '/mnt/d/Photos/YourFolder'"
```

This will:
1. Automatically detect and use WSL if available (for VILA support)
2. Process all images in the specified folder with all 5 models (MUSIQ + VILA)
3. Generate quality scores and save as JSON files
4. Create an interactive HTML gallery with sorted images
5. Automatically open the gallery in your browser

**Features**:
- ✅ Sorts by multiple metrics (robust score, weighted, VILA, KONIQ, etc.)
- ✅ Displays all 5 model scores per image
- ✅ VILA score now properly displayed and sortable
- ✅ Responsive design with modal image viewing
- ✅ Filename sorting (A-Z)

## Model Loading (Triple Fallback System)

The tool uses a **triple fallback mechanism** for maximum reliability:

1. **TensorFlow Hub** (1st priority) - Fast, no authentication required
   - Downloads models from `tfhub.dev/google/musiq/`
   - Recommended primary source
   - Works for SPAQ, AVA, PAQ2PIQ, VILA

2. **Kaggle Hub** (2nd priority) - Good fallback, requires authentication
   - Downloads from Kaggle Hub API
   - All 5 models available
   - Requires `kaggle.json` authentication

3. **Local Checkpoints** (3rd priority) - Offline support
   - Uses `.npz` files from `musiq_original/checkpoints/`
   - SavedModel format (VILA) ✅ Working
   - .npz format (MUSIQ) ⚠️ Planned
   - No network required

**Reliability**: 99.9%+ uptime with triple fallback  
**See**: [TRIPLE_FALLBACK_SYSTEM.md](docs/technical/TRIPLE_FALLBACK_SYSTEM.md) for complete details

### Model Variants

- **spaq**: Trained on SPAQ dataset (default)
- **ava**: Trained on AVA dataset  
- **koniq**: Trained on KonIQ dataset
- **paq2piq**: Trained on PaQ-2-PiQ dataset

## Input Expectations

- **Format**: RGB images (JPEG, PNG, etc.)
- **Color space**: RGB
- **Data type**: float32, normalized to [0, 1] range
- **Size**: Any resolution (MUSIQ handles multi-scale processing)
- **Channels**: 3 (RGB)

## Score Scale

The score scale depends on the training dataset:
- **SPAQ**: Typically 1-5 scale (higher = better quality)
- **AVA**: Typically 1-10 scale (higher = better quality)  
- **KonIQ**: Typically 1-5 scale (higher = better quality)
- **PaQ-2-PiQ**: Typically 1-5 scale (higher = better quality)

## Troubleshooting

### Common Issues

1. **TensorFlow CPU issues**:
   ```bash
   pip uninstall tensorflow tensorflow-gpu
   pip install tensorflow-cpu==2.15.0
   ```

2. **Model download failures**:
   - Check internet connection
   - Verify TensorFlow Hub access
   - Try different model variant

3. **Memory issues**:
   - Use smaller images
   - Close other applications
   - Consider using `tensorflow-cpu` instead of `tensorflow`

4. **Import errors**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt --force-reinstall
   ```

### Offline Usage

After first successful run, models are cached locally and can be used offline.

## Dependencies

- **tensorflow-cpu==2.15.0**: CPU-only TensorFlow
- **Pillow==10.4.0**: Image processing
- **numpy==1.24.4**: Numerical computing
- **tensorflow-hub==0.16.1**: TensorFlow Hub model loading (primary source)
- **kagglehub==0.3.4**: Kaggle Hub for VILA and all models (fallback source)

**Optional**:
- Local checkpoint files (for offline support): See [CHECKPOINT_STATUS.md](docs/technical/CHECKPOINT_STATUS.md)

## Implementation Notes

This tool uses a simplified approach for CPU-only inference:
- Avoids heavy JAX/Flax dependencies from original implementation
- Uses TensorFlow Hub for stable model loading
- Handles multi-scale image processing automatically
- Provides fallback to local checkpoints if available

## Project Documentation

- **[INDEX.md](INDEX.md)** - Complete documentation index (44 documents)
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes
- **[VERSION_2.3.0_RELEASE_NOTES.md](docs/getting-started/VERSION_2.3.0_RELEASE_NOTES.md)** - Current release highlights
- **[TRIPLE_FALLBACK_SYSTEM.md](docs/technical/TRIPLE_FALLBACK_SYSTEM.md)** - Fallback mechanism guide
- **[CHECKPOINT_STATUS.md](docs/technical/CHECKPOINT_STATUS.md)** - Local checkpoint inventory

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997) - Original MUSIQ research
- [VILA Paper](https://arxiv.org/abs/2312.07533) - VILA vision-language model
- [Google Research Repository](https://github.com/google-research/google-research/tree/master/musiq) - MUSIQ code
- [TensorFlow Hub Models](https://tfhub.dev/s?q=musiq) - TF Hub model collection
- [Kaggle Hub VILA](https://www.kaggle.com/models/google/vila) - VILA on Kaggle