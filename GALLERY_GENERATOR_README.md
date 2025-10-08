# MUSIQ Image Gallery Generator

This collection of scripts allows you to process images with MUSIQ quality assessment models and generate interactive HTML galleries.

## 🚀 Quick Start

### Option 1: Complete Workflow (Recommended)
```bash
# Process images and create gallery in one step
create_gallery.bat "C:\Path\To\Your\Images"
```

### Option 2: Two-Step Process
```bash
# Step 1: Process images with MUSIQ models
process_images.bat "C:\Path\To\Your\Images"

# Step 2: Generate gallery from existing JSON files
create_gallery.bat "C:\Path\To\Your\Images"
```

## 📁 Available Scripts

### Batch Scripts (Windows)

| Script | Purpose | Usage |
|--------|---------|-------|
| `create_gallery.bat` | **Complete workflow** - Process images + Generate gallery | `create_gallery.bat "C:\Path\To\Images"` |
| `process_images.bat` | Process images with MUSIQ models only | `process_images.bat "C:\Path\To\Images"` |
| `gallery_generator.py` | Generate gallery from existing JSON files | `python gallery_generator.py "C:\Path\To\Images"` |

### PowerShell Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `Create-Gallery.ps1` | **Complete workflow** - Process images + Generate gallery | `.\Create-Gallery.ps1 "C:\Path\To\Images"` |
| `Process-Images.ps1` | Process images with MUSIQ models only | `.\Process-Images.ps1 "C:\Path\To\Images"` |

## 🎯 What Each Script Does

### 1. Image Processing (`process_images.bat` / `Process-Images.ps1`)
- Scans the specified folder for image files (JPG, PNG, etc.)
- Runs all 4 MUSIQ models on each image:
  - **SPAQ** (0-100 scale)
  - **AVA** (1-10 scale) 
  - **KONIQ** (0-100 scale)
  - **PAQ2PIQ** (0-100 scale)
- Generates JSON files with quality scores for each image
- Creates a batch processing log file

### 2. Gallery Generation (`gallery_generator.py`)
- Reads all JSON files in the specified folder
- Creates an interactive HTML gallery with:
  - **Sortable by different metrics** (Final Robust Score, Weighted Score, Individual Model Scores, Filename, Date)
  - **Real-time statistics** (Total images, Average score, Best/Worst scores)
  - **Modal image viewing** (Click images for full-size view)
  - **Responsive design** (Works on desktop and mobile)
  - **Embedded data** (No external dependencies, works offline)

### 3. Complete Workflow (`create_gallery.bat` / `Create-Gallery.ps1`)
- Combines both steps above
- Automatically detects WSL vs Windows environment
- Processes all images with MUSIQ models
- Generates the HTML gallery
- Opens the gallery in your default web browser

## 🖼️ Gallery Features

The generated HTML gallery includes:

- **📊 Interactive Sorting**: Sort by any quality metric or filename
- **📈 Live Statistics**: Real-time updates based on current sort
- **🔍 Modal Viewing**: Click any image for full-size view
- **📱 Responsive Design**: Works on all devices
- **🎨 Modern UI**: Beautiful gradient design with smooth animations
- **⚡ Fast Loading**: Embedded data, no network requests needed

## 📋 Requirements

### For Image Processing:
- Python 3.8+ with TensorFlow
- MUSIQ models (automatically downloaded)
- GPU support (optional, for faster processing)

### For Gallery Generation:
- Python 3.6+ (any installation)
- No additional dependencies required

## 🔧 Environment Detection

The scripts automatically detect your environment:

- **WSL Environment**: Uses TensorFlow GPU with CUDA support
- **Windows Environment**: Uses standard Python installation

## 📊 Output Files

### JSON Files (per image)
```json
{
  "image_path": "D:/Photos/image.jpg",
  "image_name": "image.jpg",
  "version": "2.0.0",
  "models": {
    "spaq": {"score": 75.2, "normalized_score": 0.752},
    "ava": {"score": 6.8, "normalized_score": 0.644},
    "koniq": {"score": 82.1, "normalized_score": 0.821},
    "paq2piq": {"score": 78.5, "normalized_score": 0.785}
  },
  "summary": {
    "average_normalized_score": 0.751,
    "advanced_scoring": {
      "final_robust_score": 0.756,
      "weighted_score": 0.758,
      "median_score": 0.753
    }
  }
}
```

### HTML Gallery
- `gallery.html` - Interactive gallery file
- Self-contained (no external dependencies)
- Opens in any modern web browser

## 🎮 Usage Examples

### Process a single folder:
```bash
create_gallery.bat "D:\Photos\Vacation2025"
```

### Process multiple folders:
```bash
create_gallery.bat "D:\Photos\Vacation2025"
create_gallery.bat "D:\Photos\Wedding2025"
create_gallery.bat "D:\Photos\Family2025"
```

### Process images first, then create gallery later:
```bash
process_images.bat "D:\Photos\LargeFolder"
# ... wait for processing to complete ...
create_gallery.bat "D:\Photos\LargeFolder"
```

## 🚨 Troubleshooting

### Common Issues:

1. **"Input directory not found"**
   - Check that the folder path exists
   - Use quotes around paths with spaces

2. **"No image data found"**
   - Ensure the folder contains image files (JPG, PNG, etc.)
   - Check that JSON files were generated successfully

3. **Unicode errors**
   - The scripts now handle Unicode properly
   - If issues persist, ensure your system locale supports UTF-8

4. **WSL path issues**
   - Scripts automatically convert Windows paths to WSL paths
   - Ensure WSL is properly installed and accessible

## 📈 Performance Tips

- **GPU Processing**: Use WSL environment for faster processing
- **Batch Size**: Process large folders in smaller batches
- **Storage**: Ensure sufficient disk space for JSON files
- **Memory**: Close other applications during processing

## 🔄 Version History

- **v2.0.0**: Added weighted scoring, median scores, and robust quality assessment
- **v1.0.0**: Initial release with basic MUSIQ model support

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify all requirements are met
3. Check the batch processing log files for detailed error messages
