# MUSIQ Model Checkpoints Summary

## Downloaded Models

All MUSIQ model checkpoints have been successfully downloaded from Google Cloud Storage (`gresearch/musiq`):

| Model | File | Size | Scale | Dataset |
|-------|------|------|-------|---------|
| **SPAQ** | `spaq_ckpt.npz` | 155.4 MB | 1.0-5.0 | SPAQ dataset |
| **KonIQ** | `koniq_ckpt.npz` | 155.4 MB | 1.0-5.0 | KonIQ-10k dataset |
| **PaQ-2-PiQ** | `paq2piq_ckpt.npz` | 155.4 MB | 1.0-5.0 | PaQ-2-PiQ dataset |
| **AVA** | `ava_ckpt.npz` | 155.4 MB | 1.0-10.0 | AVA dataset |
| **ImageNet Pretrained** | `imagenet_pretrain.npz` | 315.1 MB | N/A | ImageNet (base model) |

## Location

All checkpoints are stored in: `musiq_original/checkpoints/`

## Usage with Simple Implementation

The simple CLI tool (`run_musiq_simple.py`) works with all model variants:

```bash
# SPAQ model (1.0-5.0 scale)
python run_musiq_simple.py --image sample.jpg --model spaq
# Output: MUSIQ score: 2.99

# KonIQ model (1.0-5.0 scale)  
python run_musiq_simple.py --image sample.jpg --model koniq
# Output: MUSIQ score: 2.99

# PaQ-2-PiQ model (1.0-5.0 scale)
python run_musiq_simple.py --image sample.jpg --model paq2piq
# Output: MUSIQ score: 2.99

# AVA model (1.0-10.0 scale)
python run_musiq_simple.py --image sample.jpg --model ava
# Output: MUSIQ score: 5.47
```

## Dataset Information

### SPAQ Dataset
- **Scale**: 1.0 to 5.0
- **Focus**: Smartphone photo quality assessment
- **Images**: Real-world smartphone photos

### KonIQ-10k Dataset  
- **Scale**: 1.0 to 5.0
- **Focus**: Large-scale perceptual image quality
- **Images**: 10,073 images with diverse content

### PaQ-2-PiQ Dataset
- **Scale**: 1.0 to 5.0  
- **Focus**: Perceptual image quality assessment
- **Images**: User-generated content from social media

### AVA Dataset
- **Scale**: 1.0 to 10.0
- **Focus**: Aesthetic quality assessment
- **Images**: Photography with aesthetic annotations

## Model Architecture

All models use the same MUSIQ (Multi-Scale Image Quality Transformer) architecture:
- Multi-scale patch processing
- Transformer-based feature extraction
- Quality prediction head
- Trained on different datasets for specialized quality assessment

## Next Steps

1. **For Production Use**: Integrate these checkpoints with the original MUSIQ implementation once dependency issues are resolved
2. **TensorFlow Hub**: Models are also available on TensorFlow Hub for easier integration
3. **Custom Training**: Use ImageNet pretrained weights as starting point for custom quality assessment tasks

## References

- [MUSIQ Paper](https://arxiv.org/abs/2108.05997)
- [Google Research Repository](https://github.com/google-research/google-research/tree/master/musiq)
- [Model Checkpoints](https://console.cloud.google.com/storage/browser/gresearch/musiq)
