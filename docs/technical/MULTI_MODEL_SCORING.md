# MUSIQ Multi-Model Image Quality Assessment

> **Note:** This document describes the standalone `run_all_musiq_models.py` script (the
> MUSIQ backbone). In the live pipeline, scoring is **registry-driven** via
> `MultiModelHost` (`modules/engines/host.py`): the MUSIQ family is one backend among
> several registered `IScoringModel` wrappers (LIQE, **TOPIQ**, and optional
> LLM-judge engines). Which models run, and whether each is fused or shadow, is decided by
> `scoring.models` in `config.json`; `GET /api/models` returns the live set. See
> [Weighted scoring strategy](WEIGHTED_SCORING_STRATEGY.md) for current fusion weights.

This script runs all available MUSIQ (Multi-scale Image Quality Transformer) models on an image and saves the results to a JSON file with the same name as the image.

## Features

- **Multiple Models**: The live pipeline runs SPAQ + AVA (MUSIQ family); KONIQ and PAQ2PIQ are deprecated and no longer wired
- **GPU Acceleration**: Full CUDA support with automatic CPU fallback
- **JSON Output**: Structured results with scores, ranges, and normalized values
- **Drag-and-Drop**: Easy-to-use batch and PowerShell scripts
- **Error Handling**: Graceful handling of model loading failures

## Available Models

### MUSIQ family (this script's backbone)

| Model | Dataset | Score Range | Description |
|-------|---------|-------------|-------------|
| SPAQ | SPAQ | 0.0 - 100.0 | Smartphone Photography Aesthetics Quality |
| AVA | AVA | 1.0 - 10.0 | Aesthetic Visual Analysis |
| KONIQ | KONIQ-10K | 0.0 - 100.0 | Konstanz Natural Image Quality (**deprecated** — not wired into the live registry) |
| PAQ2PIQ | PAQ2PIQ | 0.0 - 100.0 | Perceptual Assessment of Image Quality (**deprecated** — not wired into the live registry) |

### Registry models (live pipeline)

| Model | Framework | Score Range | Role |
|-------|-----------|-------------|------|
| LIQE | PyTorch | 0.0 - 1.0 | CLIP-based semantic quality (fused) |
| TOPIQ | PyTorch (pyiqa) | 0.0 - 1.0 | No-reference top-down quality (fused) |
| cursor / claude | LLM-judge | 0.0 - 1.0 | Optional LLM-as-judge engines (disabled by default) |

**QPT V2** (WIP) is implemented under `modules/qpt_v2*.py` but **not registered** in the
live registry until validation/calibration (#185).

## Usage

### Command Line

```bash
# Run all models on an image
python run_all_musiq_models.py --image /path/to/image.jpg

# Run specific models only
python run_all_musiq_models.py --image /path/to/image.jpg --models spaq ava

# Specify output directory
python run_all_musiq_models.py --image /path/to/image.jpg --output-dir /path/to/output/
```

### Drag-and-Drop (Windows)

1. **Batch Script**: Drag and drop image files onto `run_all_musiq_models_drag_drop.bat`
2. **PowerShell Script**: Drag and drop image files onto `Run-All-MUSIQ-Models.ps1`

## Output Format

The script generates a JSON file with the following structure:

```json
{
  "image_path": "/path/to/image.jpg",
  "image_name": "image.jpg",
  "device": "GPU",
  "gpu_available": true,
  "models": {
    "spaq": {
      "score": 71.14,
      "score_range": "1.0-5.0",
      "normalized_score": 17.535,
      "status": "success"
    },
    "ava": {
      "score": 5.28,
      "score_range": "1.0-10.0",
      "normalized_score": 0.475,
      "status": "success"
    },
    "koniq": {
      "score": null,
      "error": "Model not loaded",
      "status": "not_loaded"
    },
    "paq2piq": {
      "score": 78.95,
      "score_range": "1.0-5.0",
      "normalized_score": 19.489,
      "status": "success"
    }
  },
  "summary": {
    "total_models": 3,
    "successful_predictions": 3,
    "failed_predictions": 1
  }
}
```

### JSON Fields Explained

- **image_path**: Full path to the input image
- **image_name**: Just the filename
- **device**: "GPU" or "CPU" depending on what was used
- **gpu_available**: Boolean indicating GPU availability
- **models**: Object containing results for each model
  - **score**: Raw quality score from the model
  - **score_range**: Expected range for this model
  - **normalized_score**: Score normalized to 0-1 range
  - **status**: "success", "failed", or "not_loaded"
- **summary**: Overall statistics about the run
  - **average_normalized_score**: Average of all successful normalized scores (0-1 range)

## Requirements

- Python 3.8+
- TensorFlow 2.15+ with GPU support
- TensorFlow Hub
- CUDA-compatible GPU (optional, falls back to CPU)
- WSL2 with Ubuntu (for Windows users)

## Installation

1. Install dependencies:
```bash
pip install tensorflow[and-cuda]==2.15.0 tensorflow-hub==0.16.1 pillow numpy
```

2. For WSL2 users, activate the virtual environment:
```bash
source ~/.venvs/tf/bin/activate
```

## Notes

- The KONIQ model may not be available on TensorFlow Hub
- Scores are model-specific and should be interpreted within their respective ranges
- Normalized scores (0-1) can be used for cross-model comparison
- GPU acceleration significantly improves processing speed
- The script automatically handles model loading failures gracefully

## Example Results

For the sample image `20250612_037-2.jpg`:

- **SPAQ**: 71.14 (range: 0-100) - Good quality
- **AVA**: 5.28 (range: 1-10) - Above average quality  
- **KONIQ**: 74.69 (range: 0-100) - Good quality
- **PAQ2PIQ**: 78.95 (range: 0-100) - Good quality

The normalized scores allow comparison across models:
- SPAQ: 0.711 (normalized)
- AVA: 0.475 (normalized)
- KONIQ: 0.747 (normalized)
- PAQ2PIQ: 0.790 (normalized)

**Average Normalized Score: 0.681** - This gives you a single overall quality rating across all models.

## Related Documents

- [Docs index](../README.md)
- [Model weights](../reference/models/MODEL_WEIGHTS.md)
- [Weighted scoring strategy](WEIGHTED_SCORING_STRATEGY.md)
- [Model fallback mechanism](MODEL_FALLBACK_MECHANISM.md)
- [Model source testing](MODEL_SOURCE_TESTING.md)

