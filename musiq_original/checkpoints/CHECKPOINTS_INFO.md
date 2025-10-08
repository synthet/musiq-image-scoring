# MUSIQ Model Checkpoints Information

## Overview

This directory contains pre-trained model checkpoints for the MUSIQ (Multi-scale Image Quality Transformer) model. These checkpoints are trained on different datasets and can be used for image quality assessment tasks.

## Available Checkpoints

### 1. **ava_ckpt.npz**
- **Dataset**: AVA (Aesthetic Visual Analysis) dataset
- **Purpose**: Aesthetic quality assessment
- **Use Case**: General aesthetic image quality evaluation
- **Size**: ~50-100 MB

### 2. **koniq_ckpt.npz**
- **Dataset**: KonIQ-10k dataset
- **Purpose**: Perceptual image quality assessment
- **Use Case**: Technical image quality evaluation (distortions, artifacts)
- **Size**: ~50-100 MB

### 3. **paq2piq_ckpt.npz**
- **Dataset**: PaQ-2-PiQ dataset
- **Purpose**: Perceptual image quality assessment
- **Use Case**: Technical image quality evaluation
- **Size**: ~50-100 MB

### 4. **spaq_ckpt.npz**
- **Dataset**: SPAQ (Smartphone Photography Attribute and Quality) dataset
- **Purpose**: Smartphone image quality assessment
- **Use Case**: Mobile photography quality evaluation
- **Size**: ~50-100 MB

### 5. **imagenet_pretrain.npz**
- **Dataset**: ImageNet
- **Purpose**: Pre-trained weights for transfer learning
- **Use Case**: Base model for fine-tuning on custom datasets
- **Size**: ~50-100 MB

## Download Instructions

### Option 1: Direct Download from Google Cloud Storage
The checkpoints can be downloaded from the official Google Research repository:

**Main Directory**: https://console.cloud.google.com/storage/browser/gresearch/musiq

**Direct Download Links** (if available):
- `ava_ckpt.npz`: https://storage.googleapis.com/gresearch/musiq/ava_ckpt.npz
- `koniq_ckpt.npz`: https://storage.googleapis.com/gresearch/musiq/koniq_ckpt.npz
- `paq2piq_ckpt.npz`: https://storage.googleapis.com/gresearch/musiq/paq2piq_ckpt.npz
- `spaq_ckpt.npz`: https://storage.googleapis.com/gresearch/musiq/spaq_ckpt.npz
- `imagenet_pretrain.npz`: https://storage.googleapis.com/gresearch/musiq/imagenet_pretrain.npz

### Option 2: Using gsutil (Google Cloud SDK)
If you have `gsutil` installed:

```bash
# Download all checkpoints
gsutil -m cp -r gs://gresearch/musiq/* ./checkpoints/

# Or download individual files
gsutil cp gs://gresearch/musiq/ava_ckpt.npz ./checkpoints/
gsutil cp gs://gresearch/musiq/koniq_ckpt.npz ./checkpoints/
gsutil cp gs://gresearch/musiq/paq2piq_ckpt.npz ./checkpoints/
gsutil cp gs://gresearch/musiq/spaq_ckpt.npz ./checkpoints/
gsutil cp gs://gresearch/musiq/imagenet_pretrain.npz ./checkpoints/
```

### Option 3: Using wget/curl
```bash
# Download individual files
wget https://storage.googleapis.com/gresearch/musiq/ava_ckpt.npz -O ./checkpoints/ava_ckpt.npz
wget https://storage.googleapis.com/gresearch/musiq/koniq_ckpt.npz -O ./checkpoints/koniq_ckpt.npz
wget https://storage.googleapis.com/gresearch/musiq/paq2piq_ckpt.npz -O ./checkpoints/paq2piq_ckpt.npz
wget https://storage.googleapis.com/gresearch/musiq/spaq_ckpt.npz -O ./checkpoints/spaq_ckpt.npz
wget https://storage.googleapis.com/gresearch/musiq/imagenet_pretrain.npz -O ./checkpoints/imagenet_pretrain.npz
```

## Usage Examples

### Using with MUSIQ Scripts
```bash
# Run inference with SPAQ checkpoint
python3 -m musiq.run_predict_image \
  --ckpt_path=./checkpoints/spaq_ckpt.npz \
  --image_path=./sample.jpg

# Run inference with AVA checkpoint
python3 -m musiq.run_predict_image \
  --ckpt_path=./checkpoints/ava_ckpt.npz \
  --image_path=./sample.jpg
```

### Using with WSL2 + GPU Setup
```bash
# From Windows, using the provided scripts
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_musiq_gpu.py --checkpoint ./musiq_original/checkpoints/spaq_ckpt.npz --image ./sample.jpg"
```

## Model Variants

### MUSIQ (Multi-scale)
- **Input**: 3-scale input (native resolution, 224x224, 384x384)
- **Checkpoints**: All available checkpoints support this variant
- **Performance**: Higher accuracy, slower inference

### MUSIQ-single
- **Input**: Single-scale input (native resolution only)
- **Checkpoints**: Use `_SINGLE_SCALE = True` in code
- **Performance**: Faster inference, slightly lower accuracy

## File Structure
```
checkpoints/
├── CHECKPOINTS_INFO.md      # This file
├── ava_ckpt.npz            # AVA dataset checkpoint
├── koniq_ckpt.npz          # KonIQ dataset checkpoint
├── paq2piq_ckpt.npz        # PaQ-2-PiQ dataset checkpoint
├── spaq_ckpt.npz           # SPAQ dataset checkpoint
└── imagenet_pretrain.npz   # ImageNet pre-trained weights
```

## Notes

- **File Format**: All checkpoints are in NumPy compressed format (.npz)
- **Compatibility**: Compatible with TensorFlow 2.x
- **GPU Support**: Works with both CPU and GPU (CUDA) inference
- **Memory Requirements**: ~2-4 GB RAM for inference
- **License**: Check the original paper and repository for licensing terms

## Troubleshooting

### Download Issues
- If direct links don't work, try accessing through the Google Cloud Console
- Ensure you have sufficient disk space (~500 MB for all checkpoints)
- Check your internet connection for large file downloads

### Usage Issues
- Ensure TensorFlow is properly installed
- Verify checkpoint file integrity (file size should be ~50-100 MB each)
- Check file permissions if running in WSL2

## References

- **Paper**: [MUSIQ: Multi-scale Image Quality Transformer](https://arxiv.org/abs/2108.05997)
- **TensorFlow Hub**: https://tfhub.dev/s?q=musiq
- **Google Research Repository**: https://github.com/google-research/google-research/tree/master/musiq
- **Original Checkpoints**: https://console.cloud.google.com/storage/browser/gresearch/musiq

