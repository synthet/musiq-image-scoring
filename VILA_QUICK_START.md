# VILA Quick Start Guide

## ✅ Correct Model Information

**VILA Model on Kaggle Hub:**
- **URL**: https://www.kaggle.com/models/google/vila
- **Model Path**: `google/vila/tensorFlow2/image`
- **Status**: ✅ Working (as of v2.1.1)

## 🚀 Quick Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Kaggle Authentication

**Windows:**
1. Create `.kaggle` folder in your user directory:
   ```
   C:\Users\YourUsername\.kaggle\
   ```

2. Get your `kaggle.json`:
   - Go to https://www.kaggle.com
   - Click on your profile → Account
   - Scroll to API section
   - Click "Create New API Token"
   - Save the `kaggle.json` file

3. Place `kaggle.json` in:
   ```
   C:\Users\YourUsername\.kaggle\kaggle.json
   ```

**Linux/Mac:**
```bash
mkdir -p ~/.kaggle
# Place kaggle.json in ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json
```

### 3. Test VILA
```bash
python test_vila.py
```

## 📝 Usage Examples

### Single Image Assessment
```bash
# Python
python run_vila.py --image your_image.jpg

# Windows Batch
run_vila.bat "C:\Photos\image.jpg"

# Drag and drop
# Drag image onto run_vila_drag_drop.bat
```

### Multi-Model Assessment (MUSIQ + VILA)
```bash
# All 5 models
python run_all_musiq_models.py --image your_image.jpg

# Specific models
python run_all_musiq_models.py --image your_image.jpg --models koniq vila
```

### Batch Processing
```bash
python batch_process_images.py --input-dir "C:\Photos\Folder"
```

### Gallery Generation
```bash
create_gallery.bat "C:\Photos\Folder"
```

## 🎯 What You Get

### 5 Total Models

| Model | Type | Weight | Purpose |
|-------|------|--------|---------|
| KONIQ | MUSIQ | 30% | Best balance |
| SPAQ | MUSIQ | 25% | Best discrimination |
| PAQ2PIQ | MUSIQ | 20% | High-quality detection |
| **VILA** | **Vision-Language** | **15%** | **Aesthetic assessment** |
| AVA | MUSIQ | 10% | Conservative scoring |

### Output Format

```json
{
  "version": "2.1.1",
  "models": {
    "vila": {
      "score": 7.85,
      "normalized_score": 0.785,
      "status": "success"
    }
  },
  "summary": {
    "average_normalized_score": 0.735,
    "advanced_scoring": {
      "final_robust_score": 0.728
    }
  }
}
```

## ⚠️ Troubleshooting

### VILA Not Loading?

**Check Kaggle Authentication:**
```bash
python -c "import kagglehub; print(kagglehub.model_download('google/vila/tensorFlow2/image'))"
```

**Common Issues:**
1. **No kaggle.json**: Place it in `~/.kaggle/` or `%USERPROFILE%\.kaggle\`
2. **Invalid credentials**: Generate a new API token
3. **Network issues**: Check internet connection
4. **First run slow**: Model downloads (one-time, ~100MB)

### Still Not Working?

**MUSIQ will still work!** VILA is optional:
```bash
# Works without VILA
python run_all_musiq_models.py --image image.jpg --models spaq ava koniq paq2piq
```

## 📚 More Information

- **Complete Setup**: See `README_VILA.md`
- **Technical Details**: See `VILA_INTEGRATION_SUMMARY.md`
- **Path Fix**: See `VILA_MODEL_PATH_FIX.md`
- **Main README**: See `README.md`

## ✨ Quick Commands Reference

```bash
# Test everything
python test_vila.py

# Single image with VILA
python run_vila.py --image photo.jpg

# All models
python run_all_musiq_models.py --image photo.jpg

# Batch processing
python batch_process_images.py --input-dir "Photos"

# Create gallery
create_gallery.bat "Photos"
```

## 📊 Expected First Run

```
Loading VILA model from Kaggle Hub: google/vila/tensorFlow2/image
Downloading model... (this may take a few minutes)
Model downloaded to: [cache_path]
VILA model loaded successfully

VILA Model: vila
============================================================
Aesthetic Score: 7.850

JSON: {"path": "image.jpg", "model": "vila", "score": 7.85}
```

## 🎉 Success Indicators

✅ No 404 errors  
✅ Model downloads successfully  
✅ VILA scores appear in JSON output  
✅ Gallery shows 5 model scores  
✅ Version shows 2.1.1  

## 🔄 If You Used Old Version (2.1.0)

Images will be automatically reprocessed with the correct VILA model path (v2.1.1) on next run.

---

**Current Version**: 2.1.1  
**VILA Model Path**: `google/vila/tensorFlow2/image` ✅  
**Total Models**: 5 (4 MUSIQ + 1 VILA)  

