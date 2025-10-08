# MUSIQ: Multi-scale Image Quality Transformer - CLI Tool

A minimal, CPU-only Python CLI tool for scoring image aesthetic/quality using Google's MUSIQ model.

## Quick Setup

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

## Model Loading

The tool attempts to load models in this order:
1. **TensorFlow Hub** (primary method) - Downloads models from `tfhub.dev/google/musiq/`
2. **Local checkpoints** (fallback) - Uses downloaded `.npz` files from Google Cloud Storage

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
- **tensorflow-hub==0.16.1**: Model loading (optional)

## Implementation Notes

This tool uses a simplified approach for CPU-only inference:
- Avoids heavy JAX/Flax dependencies from original implementation
- Uses TensorFlow Hub for stable model loading
- Handles multi-scale image processing automatically
- Provides fallback to local checkpoints if available

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997)
- [Google Research Repository](https://github.com/google-research/google-research/tree/master/musiq)
- [TensorFlow Hub Models](https://tfhub.dev/s?q=musiq)