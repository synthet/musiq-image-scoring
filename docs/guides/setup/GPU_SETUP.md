# GPU Setup Guide

GPU-accelerated scoring for the Vexlum Scoring project using TensorFlow with CUDA support.

## Requirements

### Hardware
- NVIDIA GPU with CUDA Compute Capability 3.5 or higher
- Minimum 4GB GPU memory (8GB+ recommended)

### Software
- NVIDIA CUDA Toolkit 11.8 or 12.x
- cuDNN 8.6 or higher
- Python 3.8-3.11

## Quick Setup

### 1. Install CUDA Toolkit

Download from [NVIDIA CUDA](https://developer.nvidia.com/cuda-downloads), or use conda:

```bash
conda install cudatoolkit=11.8
```

See [INSTALL_CUDA.md](INSTALL_CUDA.md) for RTX 4060-specific instructions.

### 2. Install Python Dependencies

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements_gpu.txt
```

For WSL2 with TensorFlow GPU, see [WSL2_TENSORFLOW_GPU_SETUP.md](WSL2_TENSORFLOW_GPU_SETUP.md).

### 3. Verify GPU Setup

```bash
python -c "import tensorflow as tf; print('GPU Available:', tf.config.list_physical_devices('GPU'))"
```

## Implementation Overview

The project uses:
- **Automatic GPU detection**: Falls back to CPU if GPU unavailable
- **Multiple model loading**: TensorFlow Hub first, simplified model as fallback
- **Device-aware processing**: Ensures tensors are on the correct device (GPU/CPU)
- **Memory management**: GPU memory growth to avoid OOM errors

## Performance

| Device | Typical speed |
|--------|---------------|
| GPU | 10-50x faster than CPU |
| CPU fallback | Automatic when GPU unavailable |

## Model Variants & Score Scales

- **spaq**: SPAQ dataset — 1.0 to 5.0 (default)
- **ava**: AVA dataset — 1.0 to 10.0
- **koniq**: KonIQ dataset — 1.0 to 5.0
- **paq2piq**: PaQ-2-PiQ dataset — 1.0 to 5.0

## Troubleshooting

### CUDA Out of Memory

```bash
# Reduce image size
python run_musiq_gpu.py --image sample.jpg --target-size 128 128

# Or use CPU fallback
export CUDA_VISIBLE_DEVICES=""
```

### CUDA Not Found

```bash
nvidia-smi  # Verify CUDA installation
pip uninstall tensorflow
pip install tensorflow[and-cuda]==2.15.0
```

### TensorFlow GPU Support

```bash
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

## Related Documentation

- [WSL2_TENSORFLOW_GPU_SETUP.md](WSL2_TENSORFLOW_GPU_SETUP.md) — TensorFlow GPU in WSL2
- [INSTALL_CUDA.md](INSTALL_CUDA.md) — CUDA installation (RTX 4060)
- [ENVIRONMENTS.md](ENVIRONMENTS.md) — Virtual environment overview
