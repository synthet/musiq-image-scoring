# Instructions: Running Vexlum Scoring on Nikon NEF Files

## Quick Start

**To score all NEF files in a folder:**

```powershell
.\scripts\powershell\process_nef_folder.ps1 -FolderPath "D:\Path\To\Your\NEF\Folder"
```

## What It Does

This process will:

1. **Detect all NEF files** in the specified folder
2. **Convert RAW files** to JPEG for processing (uses rawpy library)
3. **Run Hybrid Scoring Pipeline**:
    - **Technical**: KONIQ, SPAQ, PAQ2PIQ (MUSIQ models)
    - **Aesthetic**: LIQE (PyTorch), AVA (Legacy)
4. **Calculate quality scores** and normalized ratings
5. **Write star ratings (1-5)** directly to NEF files' EXIF data
6. **Generate JSON files** with detailed scores for each image
7. **Create an HTML gallery** showing all images sorted by quality

## Example

To score all NEF files in `D:\Photos\Z6ii\28-400mm\2025\2025-10-27`:

```powershell
.\scripts\powershell\process_nef_folder.ps1 -FolderPath "D:\Photos\Z6ii\28-400mm\2025\2025-10-27"
```

## Runtime

- **Processing time**: ~2-3 minutes per image (RAW conversion takes time)
- **For 67 images**: Expect ~2-3 hours total
- **Background processing**: Script runs in WSL using GPU acceleration

## Output Files

After processing completes, you'll find:

### In the photo folder:

- **JSON files**: One per image (e.g., `DSC_5732.json`) with:
  - Individual model scores (KONIQ, SPAQ, PAQ2PIQ, LIQE, AVA)
  - Normalized scores (0-1 range)
  - Advanced scoring methods (weighted, median, trimmed mean)
  - Star rating (1-5)
  
- **gallery.html**: Interactive HTML gallery with:
  - All images sorted by quality score
  - Side-by-side comparison of all model scores
  - Automatic browser opening when complete

- **Log files**: `musiq_batch_log_YYYYMMDD_HHMMSS.log`
  - Detailed processing log
  - Each image's processing status
  - Error messages if any

- **Batch summary**: `batch_summary_YYYYMMDD_HHMMSS.json`
  - Overall statistics
  - Best/worst images
  - Processing metadata

### In the NEF files themselves:

- **Star ratings** (1-5) embedded in EXIF data
- Viewable in Lightroom, Capture One, Nikon ViewNX, etc.

## Monitoring Progress

### During processing:

Check the log file in real-time:
```powershell
Get-Content "D:\Photos\YourFolder\musiq_batch_log_YYYYMMDD_HHMMSS.log" -Wait -Tail 10
```

Or check how many images are done:
```powershell
(Get-ChildItem "D:\Photos\YourFolder\*.json" | Measure-Object).Count
```

### Check if process is running:

```powershell
wsl bash -c "ps aux | grep batch_process_images"
```

## Requirements

- WSL (Windows Subsystem for Linux) installed
- TensorFlow environment set up: `~/.venvs/tf`
- GPU: NVIDIA GPU (RTX 4060 detected in your system)
- Dependencies installed in WSL environment

## Troubleshooting

### If processing stops or fails:

1. Check the latest log file for errors
2. Verify WSL is working: `wsl --list`
3. Check GPU detection: `wsl bash -c "nvidia-smi"`

### To restart processing:

Simply run the command again. The system will skip ANY image that already has a corresponding JSON result file (ignoring version differences).

### To force re-process all images:

Delete the `.json` files in the folder, then run again.

## Alternative: Batch File

If you prefer a batch file instead of PowerShell:

```batch
process_nef_folder.bat "D:\Photos\YourFolder"
```

Or drag and drop the folder onto the `process_nef_folder.bat` file.

## What the Scores Mean

- **SPAQ** (0-100): Smartphone photography quality assessment
- **AVA** (1-10): Aesthetic visual analysis
- **KONIQ** (0-100): Real-world image quality
- **PAQ2PIQ** (0-100): Perceptual quality from patches

**Star Rating Mapping**:
- 5 stars: Score ≥ 0.9 (Excellent quality)
- 4 stars: Score ≥ 0.75 (Very good quality)
- 3 stars: Score ≥ 0.6 (Good quality)
- 2 stars: Score ≥ 0.4 (Fair quality)
- 1 star: Score < 0.4 (Poor quality)

## Notes

- Processing uses **GPU acceleration** when available (faster)
- **Rawpy library** handles RAW conversion (high quality)
- Images are processed in **original order** (filenames)
- **Temporary files** are automatically cleaned up
- All models are loaded once and reused for efficiency

