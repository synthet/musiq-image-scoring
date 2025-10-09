# Python Packages in WSL2 Ubuntu Environment

This document lists all Python packages installed in the WSL2 Ubuntu TensorFlow GPU environment.

**Environment**: WSL2 Ubuntu with TensorFlow GPU virtual environment  
**Python Version**: 3.12.3  
**Virtual Environment**: `~/.venvs/tf`  
**Generated**: October 7, 2025  

## 📦 Complete Package List

| Package | Version | Description |
|---------|---------|-------------|
| **absl-py** | 2.3.1 | Google's Python common libraries |
| **astunparse** | 1.6.3 | AST unparser for Python |
| **certifi** | 2025.10.5 | Python package for providing Mozilla's CA Bundle |
| **charset-normalizer** | 3.4.3 | Character encoding detection |
| **flatbuffers** | 25.9.23 | Memory efficient serialization library |
| **gast** | 0.6.0 | Python AST that abstracts the underlying Python version |
| **google-pasta** | 0.2.0 | A library to refactor Python code |
| **grpcio** | 1.75.1 | HTTP/2-based RPC framework |
| **h5py** | 3.14.0 | Python interface to the HDF5 binary data format |
| **idna** | 3.10 | Internationalized Domain Names in Applications |
| **imageio** | 2.37.0 | Python library for reading and writing image data |
| **keras** | 3.11.3 | Deep learning library for Python |
| **lazy_loader** | 0.4 | Lazy loading utilities for Python |
| **libclang** | 18.1.1 | Python bindings for the Clang C compiler |
| **Markdown** | 3.9 | Python implementation of Markdown |
| **markdown-it-py** | 4.0.0 | Python port of markdown-it |
| **MarkupSafe** | 3.0.3 | Safely add untrusted strings to HTML/XML markup |
| **mdurl** | 0.1.2 | Markdown URL utilities |
| **ml_dtypes** | 0.5.3 | Machine learning data types |
| **namex** | 0.1.0 | Name extraction utilities |
| **networkx** | 3.5 | Python package for creating and manipulating graphs |
| **numpy** | 2.1.3 | Fundamental package for scientific computing |
| **nvidia-cublas-cu12** | 12.9.1.4 | NVIDIA cuBLAS library for CUDA 12 |
| **nvidia-cuda-cupti-cu12** | 12.9.79 | NVIDIA CUDA Profiling Tools Interface |
| **nvidia-cuda-nvcc-cu12** | 12.9.86 | NVIDIA CUDA Compiler |
| **nvidia-cuda-nvrtc-cu12** | 12.9.86 | NVIDIA CUDA Runtime Compilation |
| **nvidia-cuda-runtime-cu12** | 12.9.79 | NVIDIA CUDA Runtime library |
| **nvidia-cudnn-cu12** | 9.13.1.26 | NVIDIA cuDNN library for CUDA 12 |
| **nvidia-cufft-cu12** | 11.4.1.4 | NVIDIA cuFFT library for CUDA 12 |
| **nvidia-curand-cu12** | 10.3.10.19 | NVIDIA cuRAND library for CUDA 12 |
| **nvidia-cusolver-cu12** | 11.7.5.82 | NVIDIA cuSOLVER library for CUDA 12 |
| **nvidia-cusparse-cu12** | 12.5.10.65 | NVIDIA cuSPARSE library for CUDA 12 |
| **nvidia-nccl-cu12** | 2.28.3 | NVIDIA Collective Communications Library |
| **nvidia-nvjitlink-cu12** | 12.9.86 | NVIDIA JIT Link library for CUDA 12 |
| **opencv-python** | 4.12.0.88 | OpenCV Python bindings |
| **opt_einsum** | 3.4.0 | Optimized einsum function |
| **optree** | 0.17.0 | Optimized tree operations |
| **packaging** | 25.0 | Core utilities for Python packages |
| **pillow** | 11.3.0 | Python Imaging Library (PIL) |
| **pip** | 25.2 | Python package installer |
| **protobuf** | 5.29.5 | Protocol Buffers for Python |
| **Pygments** | 2.19.2 | Python syntax highlighter |
| **requests** | 2.32.5 | HTTP library for Python |
| **rich** | 14.1.0 | Rich text and beautiful formatting |
| **scikit-image** | 0.25.2 | Image processing library for Python |
| **scipy** | 1.16.2 | Scientific computing library |
| **setuptools** | 80.9.0 | Python packaging utilities |
| **six** | 1.17.0 | Python 2 and 3 compatibility utilities |
| **tensorboard** | 2.20.0 | TensorFlow visualization toolkit |
| **tensorboard-data-server** | 0.7.2 | TensorBoard data server |
| **tensorflow** | 2.20.0 | Machine learning platform |
| **termcolor** | 3.1.0 | ANSI color formatting for terminal output |
| **tifffile** | 2025.10.4 | Read and write TIFF files |
| **typing_extensions** | 4.15.0 | Backported type hints for Python |
| **urllib3** | 2.5.0 | HTTP client library |
| **Werkzeug** | 3.1.3 | WSGI utility library |
| **wheel** | 0.45.1 | Built-package format for Python |
| **wrapt** | 1.17.3 | Decorators, wrappers and monkey patching |

## 🎯 Package Categories

### Core Machine Learning
- **tensorflow** (2.20.0) - Main ML framework
- **keras** (3.11.3) - High-level neural networks API
- **numpy** (2.1.3) - Numerical computing
- **scipy** (1.16.2) - Scientific computing

### GPU Acceleration (NVIDIA CUDA)
- **nvidia-cudnn-cu12** (9.13.1.26) - Deep neural network library
- **nvidia-cublas-cu12** (12.9.1.4) - Basic linear algebra subprograms
- **nvidia-cuda-runtime-cu12** (12.9.79) - CUDA runtime
- **nvidia-cuda-nvcc-cu12** (12.9.86) - CUDA compiler
- **nvidia-cufft-cu12** (11.4.1.4) - Fast Fourier transform library
- **nvidia-curand-cu12** (10.3.10.19) - Random number generation
- **nvidia-cusolver-cu12** (11.7.5.82) - Dense and sparse linear solvers
- **nvidia-cusparse-cu12** (12.5.10.65) - Sparse matrix operations
- **nvidia-nccl-cu12** (2.28.3) - Multi-GPU communication

### Image Processing
- **opencv-python** (4.12.0.88) - Computer vision library
- **pillow** (11.3.0) - Python Imaging Library
- **scikit-image** (0.25.2) - Image processing algorithms
- **imageio** (2.37.0) - Image I/O library
- **tifffile** (2025.10.4) - TIFF file support

### Data Handling
- **h5py** (3.14.0) - HDF5 file format support
- **pandas** - Not installed (can be added if needed)
- **matplotlib** - Not installed (can be added if needed)

### Development Tools
- **pip** (25.2) - Package installer
- **setuptools** (80.9.0) - Package building utilities
- **wheel** (0.45.1) - Built-package format

### Visualization
- **tensorboard** (2.20.0) - TensorFlow visualization
- **rich** (14.1.0) - Rich text formatting

## 🔧 Installation Commands

To recreate this environment:

```bash
# Create virtual environment
python3 -m venv ~/.venvs/tf
source ~/.venvs/tf/bin/activate

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install TensorFlow with CUDA support
pip install 'tensorflow[and-cuda]'

# Install additional packages
pip install opencv-python scikit-image pillow
```

## 📊 Environment Summary

- **Total Packages**: 56
- **Core ML Packages**: 4 (TensorFlow, Keras, NumPy, SciPy)
- **NVIDIA CUDA Packages**: 9
- **Image Processing Packages**: 5
- **Development Tools**: 3
- **Visualization Tools**: 2

## 🚀 Performance Notes

This environment is optimized for:
- **GPU-accelerated machine learning** with TensorFlow 2.20.0
- **Image processing** with OpenCV and scikit-image
- **CUDA 12.0** compatibility
- **High-performance computing** with optimized libraries

## 🔄 Maintenance

To update packages:
```bash
source ~/.venvs/tf/bin/activate
pip list --outdated
pip install --upgrade package_name
```

To export requirements:
```bash
source ~/.venvs/tf/bin/activate
pip freeze > requirements.txt
```

To install from requirements:
```bash
source ~/.venvs/tf/bin/activate
pip install -r requirements.txt
```
