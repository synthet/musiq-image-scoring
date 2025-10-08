# MUSIQ: Multi-scale Image Quality Transformer - Simple CLI Tool

A minimal, CPU-only Python CLI tool for scoring image aesthetic/quality using a simplified MUSIQ-style algorithm.

## Quick Setup

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements_simple.txt
```

## Usage

```bash
python run_musiq_simple.py --image sample.jpg
```

### Options

- `--image`: Path to input image (required)
- `--model`: Model variant - `spaq` (default), `ava`, `koniq`, or `paq2piq`
- `--save-preprocessed`: Save preprocessed image for debugging

### Examples

```bash
# Basic usage
python run_musiq_simple.py --image sample.jpg

# Use different model variant
python run_musiq_simple.py --image sample.jpg --model ava

# Save preprocessed image
python run_musiq_simple.py --image sample.jpg --save-preprocessed preprocessed.jpg
```

## Output Format

The tool outputs two lines:
1. Human-readable score: `MUSIQ score: 2.99`
2. JSON format: `{"path": "sample.jpg", "score": 2.99, "model": "spaq"}`

## Model Variants & Score Scales

- **spaq**: Trained on SPAQ dataset - Scale: 1.0 to 5.0 (default)
- **ava**: Trained on AVA dataset - Scale: 1.0 to 10.0
- **koniq**: Trained on KonIQ dataset - Scale: 1.0 to 5.0
- **paq2piq**: Trained on PaQ-2-PiQ dataset - Scale: 1.0 to 5.0

## Implementation Details

This is a **simplified demonstration** that calculates image quality based on:
- **Sharpness**: Laplacian variance (higher = sharper)
- **Contrast**: Standard deviation of pixel values (higher = more contrast)
- **Brightness**: Optimal around 0.5 (penalizes too dark/bright images)
- **Colorfulness**: Color channel standard deviation (higher = more colorful)
- **Dynamic Range**: Difference between min/max values (higher = better range)

The algorithm combines these metrics with weighted averaging to produce a quality score.

## Input Expectations

- **Format**: RGB images (JPEG, PNG, etc.)
- **Color space**: RGB
- **Size**: Any resolution (automatically processed)
- **Channels**: 3 (RGB)

## Example Results

```bash
$ python run_musiq_simple.py --image sample.jpg
MUSIQ score: 2.99
{"path": "sample.jpg", "score": 2.99, "model": "spaq"}

$ python run_musiq_simple.py --image sample.jpg --model ava
MUSIQ score: 5.47
{"path": "sample.jpg", "score": 5.47, "model": "ava"}
```

## Dependencies

- **numpy==1.26.4**: Numerical computing
- **Pillow==10.4.0**: Image processing
- **scipy==1.16.2**: Scientific computing (for Laplacian operator)

## Production Use

For production use with actual MUSIQ models:

1. **TensorFlow Hub**: Use models from `tfhub.dev/google/musiq/`
2. **Local Checkpoints**: Download from Google Cloud Storage `gresearch/musiq`
3. **Kaggle Models**: Check for official Kaggle model integration

This simplified implementation provides a foundation that can be extended with actual MUSIQ model loading.

## Troubleshooting

### Common Issues

1. **Import errors**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements_simple.txt --force-reinstall
   ```

2. **Image loading errors**:
   - Ensure image file exists and is readable
   - Check image format (JPEG, PNG supported)
   - Verify file permissions

3. **Memory issues**:
   - Use smaller images for processing
   - Close other applications

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997)
- [Google Research Repository](https://github.com/google-research/google-research/tree/master/musiq)
- [TensorFlow Hub Models](https://tfhub.dev/s?q=musiq)

## License

This implementation is for educational and demonstration purposes. The original MUSIQ research is from Google Research.
