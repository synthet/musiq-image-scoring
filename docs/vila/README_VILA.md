# VILA Model Integration

This document explains how to use Google's VILA (Vision-Language) models for image aesthetic assessment in this project.

## What is VILA?

VILA (Vision-Language Intelligence and edge AI) is a vision-language model developed by Google that combines visual and language understanding for tasks like:
- Image aesthetic assessment
- Image quality evaluation
- Visual reasoning
- Image ranking and comparison

## Available Models

### VILA (Image Assessment Model)
- **Model ID**: `google/vila/tensorFlow2/image`
- **Purpose**: Image aesthetic assessment using vision-language understanding
- **Score Range**: 0-1 (normalized aesthetic quality score)
- **Use Case**: Evaluating overall image aesthetics and quality

## Setup Requirements

### 1. Install Dependencies

```bash
pip install kagglehub==0.3.4
```

This is included in the standard `requirements.txt`.

### 2. Kaggle Authentication

VILA models are hosted on Kaggle Hub and require authentication:

#### Step 1: Create a Kaggle Account
1. Go to [kaggle.com](https://www.kaggle.com)
2. Sign up or log in

#### Step 2: Generate API Token
1. Go to your Kaggle Account Settings
2. Navigate to "API" section
3. Click "Create New API Token"
4. Download `kaggle.json` file

#### Step 3: Place kaggle.json

**On Windows:**
```
C:\Users\<YourUsername>\.kaggle\kaggle.json
```

**On Linux/Mac:**
```
~/.kaggle/kaggle.json
```

**Or set environment variable:**
```bash
export KAGGLE_CONFIG_DIR=/path/to/kaggle/config
```

#### Step 4: Set Permissions (Linux/Mac only)
```bash
chmod 600 ~/.kaggle/kaggle.json
```

## Usage

### Standalone VILA Scorer

```bash
# Use VILA model
python run_vila.py --image sample.jpg
```

### Integrated with MUSIQ Models

VILA models are automatically integrated into the multi-model system:

```bash
# Run all models including VILA
python run_all_musiq_models.py --image sample.jpg

# Run specific models including VILA
python run_all_musiq_models.py --image sample.jpg --models koniq vila

# Batch processing with VILA
python batch_process_images.py --input-dir "C:\Photos\Export\2025"
```

### Gallery Generation with VILA

VILA scores are automatically included when generating galleries:

```bash
create_gallery.bat "C:\Photos\Export\2025"
```

## Output Format

### Standalone VILA Output

```
VILA Model: vila
============================================================
Aesthetic Score: 7.850

All Model Outputs:
  output_0: 7.850

JSON: {"path": "sample.jpg", "model": "vila", "score": 7.85, "outputs": {"output_0": 7.85}}
```

### Integrated Output (JSON)

When using `run_all_musiq_models.py`, VILA scores are included alongside MUSIQ scores:

```json
{
  "version": "2.1.0",
  "image_path": "sample.jpg",
  "models": {
    "koniq": {
      "score": 68.45,
      "score_range": "0.0-100.0",
      "normalized_score": 0.685,
      "status": "success"
    },
    "vila": {
      "score": 0.785,
      "score_range": "0.0-1.0",
      "normalized_score": 0.785,
      "status": "success"
    }
  },
  "summary": {
    "average_normalized_score": 0.735,
    "advanced_scoring": {
      "weighted_score": 0.720,
      "final_robust_score": 0.728
    }
  }
}
```

## Model Weights in Scoring

VILA model is weighted in the final score calculation:

- **KONIQ**: 30% (highest weight - best balance)
- **SPAQ**: 25%
- **PAQ2PIQ**: 20%
- **VILA**: 15% (vision-language aesthetics)
- **AVA**: 10%

## Troubleshooting

### Error: "No kaggle.json found"

**Solution:** Follow the authentication steps above to set up your Kaggle credentials.

### Error: "Model download failed"

**Possible causes:**
1. No internet connection
2. Kaggle credentials not set up correctly
3. Kaggle API token expired

**Solution:**
1. Check internet connection
2. Verify `kaggle.json` is in the correct location
3. Generate a new API token if needed

### Error: "VILA models not loading"

**Solution:** 
- Make sure `kagglehub` package is installed: `pip install kagglehub==0.3.4`
- Verify Kaggle authentication is set up correctly
- Check that you have accepted the model's terms of use on Kaggle

### Slow First Run

The first time you use VILA models, they need to be downloaded from Kaggle. This can take several minutes depending on your internet connection. Subsequent runs will use the cached models.

## Integration with Existing Workflows

VILA models are fully integrated with existing batch processing and gallery generation workflows:

1. **Batch Processing**: VILA scores are automatically calculated when processing image directories
2. **Gallery Generation**: VILA scores contribute to the final weighted score used for sorting images
3. **Version Tracking**: Results include version numbers to track which models were used
4. **Caching**: Already-processed images with VILA scores are skipped unless the version changes

## Model Comparison

| Feature | MUSIQ Models | VILA Models |
|---------|-------------|-------------|
| **Type** | Pure image quality | Vision-language |
| **Training** | Specific quality datasets | Multi-modal vision-language |
| **Strengths** | Precise quality metrics | Holistic aesthetic understanding |
| **Best For** | Technical quality | Overall aesthetics |
| **Speed** | Fast | Moderate |

## Best Practices

1. **Use VILA alongside MUSIQ**: The combination provides both technical quality (MUSIQ) and aesthetic appeal (VILA)
2. **Check authentication early**: Set up Kaggle credentials before batch processing large image sets
3. **Monitor first run**: First model download can take time, ensure it completes successfully
4. **Review weighted scores**: VILA contributes 15-20% to final scores, providing aesthetic context

## References

- [VILA on Kaggle](https://www.kaggle.com/models/google/vila)
- [VILA Research Paper](https://arxiv.org/abs/2312.07533)
- [NVIDIA VILA Blog](https://developer.nvidia.com/blog/visual-language-intelligence-and-edge-ai-2-0)
- [Google Research VILA](https://github.com/google-research/google-research/tree/master/vila)

