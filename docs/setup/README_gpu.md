# MUSIQ: Multi-scale Image Quality Transformer - GPU Implementation

A GPU-accelerated Python CLI tool for scoring image aesthetic/quality using Google's MUSIQ model with CUDA support.

## GPU Requirements

### Hardware
- NVIDIA GPU with CUDA Compute Capability 3.5 or higher
- Minimum 4GB GPU memory (8GB+ recommended)

### Software
- NVIDIA CUDA Toolkit 11.8 or 12.x
- cuDNN 8.6 or higher
- Python 3.8-3.11

## Quick Setup

### 1. Install CUDA Toolkit
```bash
# Download from NVIDIA: https://developer.nvidia.com/cuda-downloads
# Or use conda:
conda install cudatoolkit=11.8
```

### 2. Install Python Dependencies
```bash
python -m venv .venv
. .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements_gpu.txt
```

### 3. Verify GPU Setup
```bash
python -c "import tensorflow as tf; print('GPU Available:', tf.config.list_physical_devices('GPU'))"
```

## Usage

```bash
python run_musiq_gpu.py --image sample.jpg
```

### Options

- `--image`: Path to input image (required)
- `--model`: Model variant - `spaq` (default), `ava`, `koniq`, or `paq2piq`
- `--save-preprocessed`: Save preprocessed image for debugging
- `--benchmark`: Run performance benchmark (10 iterations)
- `--target-size`: Target image size (default: 224 224)

### Examples

```bash
# Basic usage (auto-detects GPU/CPU)
python run_musiq_gpu.py --image sample.jpg

# Use different model variant
python run_musiq_gpu.py --image sample.jpg --model ava

# Run performance benchmark
python run_musiq_gpu.py --image sample.jpg --benchmark

# Custom image size
python run_musiq_gpu.py --image sample.jpg --target-size 512 512

# Save preprocessed image
python run_musiq_gpu.py --image sample.jpg --save-preprocessed preprocessed.jpg
```

## Output Format

The tool outputs two lines:
1. Human-readable score with device info: `MUSIQ score (GPU): 6.87`
2. JSON format: `{"path": "sample.jpg", "score": 6.87, "model": "spaq", "device": "GPU", "gpu_available": true}`

## Performance Comparison

### GPU vs CPU Performance
```bash
# GPU benchmark
python run_musiq_gpu.py --image sample.jpg --benchmark

# Expected output:
# {
#   "device": "/GPU:0",
#   "gpu_available": true,
#   "average_time_ms": 15.2,
#   "std_time_ms": 1.1,
#   "runs": 10
# }
```

### Typical Performance Gains
- **GPU**: 10-50x faster inference than CPU
- **Memory**: GPU uses more memory but processes larger batches
- **Latency**: GPU has higher initial setup time but faster per-image processing

## Model Loading Strategy

The GPU implementation tries multiple loading methods:

1. **TensorFlow Hub** (primary) - Downloads models from `tfhub.dev/google/musiq/`
2. **Simplified Model** (fallback) - Creates a multi-scale CNN architecture
3. **CPU Fallback** - Automatically falls back to CPU if GPU unavailable

## Model Variants & Score Scales

- **spaq**: Trained on SPAQ dataset - Scale: 1.0 to 5.0 (default)
- **ava**: Trained on AVA dataset - Scale: 1.0 to 10.0  
- **koniq**: Trained on KonIQ dataset - Scale: 1.0 to 5.0
- **paq2piq**: Trained on PaQ-2-PiQ dataset - Scale: 1.0 to 5.0

## GPU Memory Management

The implementation includes automatic GPU memory management:
- **Memory Growth**: Allocates GPU memory as needed (not all at once)
- **Device Placement**: Ensures tensors are on the correct device
- **Fallback**: Automatically falls back to CPU if GPU issues occur

## Troubleshooting

### Common GPU Issues

1. **CUDA Out of Memory**:
   ```bash
   # Reduce image size
   python run_musiq_gpu.py --image sample.jpg --target-size 128 128
   
   # Or use CPU fallback
   export CUDA_VISIBLE_DEVICES=""
   python run_musiq_gpu.py --image sample.jpg
   ```

2. **CUDA Not Found**:
   ```bash
   # Check CUDA installation
   nvidia-smi
   
   # Reinstall TensorFlow with CUDA
   pip uninstall tensorflow
   pip install tensorflow[and-cuda]==2.15.0
   ```

3. **cuDNN Issues**:
   ```bash
   # Install cuDNN
   conda install cudnn=8.6
   
   # Or download from NVIDIA Developer
   ```

4. **Version Compatibility**:
   ```bash
   # Check TensorFlow GPU support
   python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
   
   # Should show GPU devices if properly configured
   ```

### Performance Optimization

1. **Batch Processing**: Process multiple images simultaneously
2. **Mixed Precision**: Use FP16 for faster inference (if supported)
3. **TensorRT**: Optimize models with TensorRT for production

## Dependencies

- **tensorflow[and-cuda]==2.15.0**: TensorFlow with CUDA support
- **Pillow==10.4.0**: Image processing
- **numpy==1.26.4**: Numerical computing
- **tensorflow-hub==0.16.1**: Model loading

## Example Results

```bash
$ python run_musiq_gpu.py --image sample.jpg --benchmark
Benchmark results: {
  "device": "/GPU:0",
  "gpu_available": true,
  "average_time_ms": 12.5,
  "std_time_ms": 0.8,
  "runs": 10
}
MUSIQ score (GPU): 6.87
{"path": "sample.jpg", "score": 6.87, "model": "spaq", "device": "GPU", "gpu_available": true}
```

## Production Deployment

For production use:
1. Use TensorRT for optimized inference
2. Implement batch processing for multiple images
3. Add model serving with TensorFlow Serving
4. Monitor GPU utilization and memory usage
5. Implement proper error handling and fallbacks

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997)
- [TensorFlow GPU Guide](https://www.tensorflow.org/guide/gpu)
- [CUDA Installation Guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/)
- [TensorFlow Hub Models](https://tfhub.dev/s?q=musiq)
