@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    MUSIQ Image Gallery Generator
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: create_gallery_simple.bat "C:\Path\To\Your\Images"
    echo.
    echo Example: create_gallery_simple.bat "D:\Photos\Export\2025"
    echo.
    pause
    exit /b 1
)

set "INPUT_FOLDER=%~1"
set "OUTPUT_FILE=%~1\gallery.html"

echo Input folder: %INPUT_FOLDER%
echo Output file: %OUTPUT_FILE%
echo.

REM Check if input folder exists
if not exist "%INPUT_FOLDER%" (
    echo ERROR: Folder does not exist: %INPUT_FOLDER%
    echo.
    pause
    exit /b 1
)

echo Creating gallery for images in: %INPUT_FOLDER%
echo.

REM Create a simple Python script
echo import os > temp_script.py
echo import json >> temp_script.py
echo import glob >> temp_script.py
echo import sys >> temp_script.py
echo. >> temp_script.py
echo def main(): >> temp_script.py
echo     directory = sys.argv[1] >> temp_script.py
echo     print(f"Loading data from: {directory}") >> temp_script.py
echo     json_files = glob.glob(os.path.join(directory, "*.json")) >> temp_script.py
echo     print(f"Found {len(json_files)} JSON files") >> temp_script.py
echo     image_data = [] >> temp_script.py
echo     for json_file in json_files: >> temp_script.py
echo         try: >> temp_script.py
echo             with open(json_file, 'r', encoding='utf-8') as f: >> temp_script.py
echo                 data = json.load(f) >> temp_script.py
echo             filename = os.path.basename(json_file) >> temp_script.py
echo             if any(skip in filename.lower() for skip in ['analysis', 'batch_summary', 'weighted_scoring', 'cluster_summary', 'image_data', 'gallery']): >> temp_script.py
echo                 continue >> temp_script.py
echo             if 'image_path' in data and 'models' in data: >> temp_script.py
echo                 image_path = data['image_path'] >> temp_script.py
echo                 if image_path.startswith('/mnt/d/'): >> temp_script.py
echo                     image_path = image_path.replace('/mnt/d/', 'D:/') >> temp_script.py
echo                 elif not image_path.startswith('D:/'): >> temp_script.py
echo                     image_path = os.path.basename(image_path) >> temp_script.py
echo                 data['image_path'] = image_path >> temp_script.py
echo                 image_data.append(data) >> temp_script.py
echo         except Exception as e: >> temp_script.py
echo             print(f"Error loading {json_file}: {e}") >> temp_script.py
echo     print(f"Loaded {len(image_data)} valid records") >> temp_script.py
echo     if not image_data: >> temp_script.py
echo         print("No valid image data found!") >> temp_script.py
echo         return >> temp_script.py
echo     image_data.sort(key=lambda x: x.get('summary', {}).get('advanced_scoring', {}).get('final_robust_score', 0), reverse=True) >> temp_script.py
echo     json_data = json.dumps(image_data, indent=2, ensure_ascii=False) >> temp_script.py
echo     html_content = f"""^<!DOCTYPE html^> >> temp_script.py
echo ^<html lang="en"^> >> temp_script.py
echo ^<head^> >> temp_script.py
echo     ^<meta charset="UTF-8"^> >> temp_script.py
echo     ^<meta name="viewport" content="width=device-width, initial-scale=1.0"^> >> temp_script.py
echo     ^<title^>MUSIQ Image Quality Gallery^</title^> >> temp_script.py
echo     ^<style^> >> temp_script.py
echo         body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }} >> temp_script.py
echo         .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }} >> temp_script.py
echo         .header {{ text-align: center; margin-bottom: 30px; }} >> temp_script.py
echo         .header h1 {{ color: #333; font-size: 2em; margin-bottom: 10px; }} >> temp_script.py
echo         .controls {{ display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }} >> temp_script.py
echo         select {{ padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px; }} >> temp_script.py
echo         .stats {{ display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }} >> temp_script.py
echo         .stat-item {{ text-align: center; padding: 10px 15px; background: #667eea; color: white; border-radius: 5px; }} >> temp_script.py
echo         .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px; }} >> temp_script.py
echo         .image-card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); cursor: pointer; }} >> temp_script.py
echo         .image-container {{ width: 100%%; height: 150px; overflow: hidden; }} >> temp_script.py
echo         .image-container img {{ width: 100%%; height: 100%%; object-fit: cover; }} >> temp_script.py
echo         .image-info {{ padding: 10px; }} >> temp_script.py
echo         .image-name {{ font-weight: bold; margin-bottom: 8px; font-size: 0.9em; }} >> temp_script.py
echo         .scores {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5px; font-size: 0.8em; }} >> temp_script.py
echo         .score-item {{ display: flex; justify-content: space-between; padding: 3px 5px; background: #f8f9fa; border-radius: 3px; }} >> temp_script.py
echo         .primary-score {{ background: #667eea; color: white; }} >> temp_script.py
echo         .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%%; height: 100%%; background-color: rgba(0,0,0,0.9); }} >> temp_script.py
echo         .modal-content {{ position: absolute; top: 50%%; left: 50%%; transform: translate(-50%%, -50%%); max-width: 90%%; max-height: 90%%; }} >> temp_script.py
echo         .modal-content img {{ width: 100%%; height: 100%%; object-fit: contain; }} >> temp_script.py
echo         .close {{ position: absolute; top: 20px; right: 35px; color: #f1f1f1; font-size: 40px; font-weight: bold; cursor: pointer; }} >> temp_script.py
echo     ^</style^> >> temp_script.py
echo ^</head^> >> temp_script.py
echo ^<body^> >> temp_script.py
echo     ^<div class="container"^> >> temp_script.py
echo         ^<div class="header"^> >> temp_script.py
echo             ^<h1^>&#9733; MUSIQ Image Quality Gallery^</h1^> >> temp_script.py
echo             ^<p^>Browse your images sorted by quality metrics^</p^> >> temp_script.py
echo         ^</div^> >> temp_script.py
echo         ^<div class="controls"^> >> temp_script.py
echo             ^<select id="sortMetric"^> >> temp_script.py
echo                 ^<option value="final_robust_score"^>Final Robust Score^</option^> >> temp_script.py
echo                 ^<option value="average_normalized_score"^>Average Score^</option^> >> temp_script.py
echo                 ^<option value="spaq_score"^>SPAQ Score^</option^> >> temp_script.py
echo                 ^<option value="ava_score"^>AVA Score^</option^> >> temp_script.py
echo                 ^<option value="koniq_score"^>KONIQ Score^</option^> >> temp_script.py
echo                 ^<option value="paq2piq_score"^>PAQ2PIQ Score^</option^> >> temp_script.py
echo                 ^<option value="filename"^>Filename^</option^> >> temp_script.py
echo             ^</select^> >> temp_script.py
echo             ^<select id="sortOrder"^> >> temp_script.py
echo                 ^<option value="desc"^>Highest First^</option^> >> temp_script.py
echo                 ^<option value="asc"^>Lowest First^</option^> >> temp_script.py
echo             ^</select^> >> temp_script.py
echo         ^</div^> >> temp_script.py
echo         ^<div class="stats" id="stats"^> >> temp_script.py
echo             ^<div class="stat-item"^>^<div id="totalImages"^-^</div^>^<div^>Total Images^</div^>^</div^> >> temp_script.py
echo             ^<div class="stat-item"^>^<div id="avgScore"^-^</div^>^<div^>Avg Score^</div^>^</div^> >> temp_script.py
echo             ^<div class="stat-item"^>^<div id="bestScore"^-^</div^>^<div^>Best Score^</div^>^</div^> >> temp_script.py
echo             ^<div class="stat-item"^>^<div id="worstScore"^-^</div^>^<div^>Worst Score^</div^>^</div^> >> temp_script.py
echo         ^</div^> >> temp_script.py
echo         ^<div id="gallery" class="gallery"^>^</div^> >> temp_script.py
echo     ^</div^> >> temp_script.py
echo     ^<div id="modal" class="modal"^> >> temp_script.py
echo         ^<span class="close"^>^&times;^</span^> >> temp_script.py
echo         ^<div class="modal-content"^> >> temp_script.py
echo             ^<img id="modalImage" src="" alt=""^> >> temp_script.py
echo         ^</div^> >> temp_script.py
echo     ^</div^> >> temp_script.py
echo     ^<script^> >> temp_script.py
echo         const imageData = {json_data}; >> temp_script.py
echo         let currentSort = 'final_robust_score'; >> temp_script.py
echo         let currentOrder = 'desc'; >> temp_script.py
echo         function getScore(image, metric) { >> temp_script.py
echo             switch (metric) { >> temp_script.py
echo                 case 'final_robust_score': return image.summary?.advanced_scoring?.final_robust_score || image.summary?.average_normalized_score || 0; >> temp_script.py
echo                 case 'average_normalized_score': return image.summary?.average_normalized_score || 0; >> temp_script.py
echo                 case 'spaq_score': return image.models?.spaq?.normalized_score || 0; >> temp_script.py
echo                 case 'ava_score': return image.models?.ava?.normalized_score || 0; >> temp_script.py
echo                 case 'koniq_score': return image.models?.koniq?.normalized_score || 0; >> temp_script.py
echo                 case 'paq2piq_score': return image.models?.paq2piq?.normalized_score || 0; >> temp_script.py
echo                 case 'filename': return image.image_name || ''; >> temp_script.py
echo                 default: return 0; >> temp_script.py
echo             } >> temp_script.py
echo         } >> temp_script.py
echo         function updateStats() { >> temp_script.py
echo             if (imageData.length === 0) return; >> temp_script.py
echo             const scores = imageData.map(img =^> getScore(img, currentSort)).filter(s =^> s !== null); >> temp_script.py
echo             document.getElementById('totalImages').textContent = imageData.length; >> temp_script.py
echo             document.getElementById('avgScore').textContent = scores.length ^> 0 ? (scores.reduce((a, b) =^> a + b, 0) / scores.length).toFixed(3) : '-'; >> temp_script.py
echo             document.getElementById('bestScore').textContent = scores.length ^> 0 ? Math.max(...scores).toFixed(3) : '-'; >> temp_script.py
echo             document.getElementById('worstScore').textContent = scores.length ^> 0 ? Math.min(...scores).toFixed(3) : '-'; >> temp_script.py
echo         } >> temp_script.py
echo         function sortImages() { >> temp_script.py
echo             imageData.sort((a, b) =^> { >> temp_script.py
echo                 const scoreA = getScore(a, currentSort); >> temp_script.py
echo                 const scoreB = getScore(b, currentSort); >> temp_script.py
echo                 if (currentSort === 'filename') { >> temp_script.py
echo                     return currentOrder === 'asc' ? scoreA.localeCompare(scoreB) : scoreB.localeCompare(scoreA); >> temp_script.py
echo                 } >> temp_script.py
echo                 return currentOrder === 'asc' ? scoreA - scoreB : scoreB - scoreA; >> temp_script.py
echo             }); >> temp_script.py
echo         } >> temp_script.py
echo         function renderGallery() { >> temp_script.py
echo             sortImages(); >> temp_script.py
echo             updateStats(); >> temp_script.py
echo             const gallery = document.getElementById('gallery'); >> temp_script.py
echo             gallery.innerHTML = ''; >> temp_script.py
echo             imageData.forEach((image, index) =^> { >> temp_script.py
echo                 const card = document.createElement('div'); >> temp_script.py
echo                 card.className = 'image-card'; >> temp_script.py
echo                 const imageName = image.image_name || 'Unknown'; >> temp_script.py
echo                 const imagePath = image.image_path || ''; >> temp_script.py
echo                 const models = image.models || {}; >> temp_script.py
echo                 const summary = image.summary || {}; >> temp_script.py
echo                 const primaryScore = getScore(image, currentSort); >> temp_script.py
echo                 const primaryLabel = currentSort.replace('_score', '').replace('_', ' ').toUpperCase(); >> temp_script.py
echo                 card.innerHTML = `^<div class="image-container"^>^<img src="${imagePath}" alt="${imageName}" loading="lazy"^>^</div^>^<div class="image-info"^>^<div class="image-name"^>${imageName}^</div^>^<div class="scores"^>^<div class="score-item primary-score"^>^<span^>${primaryLabel}^</span^>^<span^>${primaryScore.toFixed(3)}^</span^>^</div^>^<div class="score-item"^>^<span^>Avg^</span^>^<span^>${(summary.average_normalized_score || 0).toFixed(3)}^</span^>^</div^>^<div class="score-item"^>^<span^>SPAQ^</span^>^<span^>${(models.spaq?.normalized_score || 0).toFixed(3)}^</span^>^</div^>^<div class="score-item"^>^<span^>AVA^</span^>^<span^>${(models.ava?.normalized_score || 0).toFixed(3)}^</span^>^</div^>^<div class="score-item"^>^<span^>KONIQ^</span^>^<span^>${(models.koniq?.normalized_score || 0).toFixed(3)}^</span^>^</div^>^<div class="score-item"^>^<span^>PAQ2PIQ^</span^>^<span^>${(models.paq2piq?.normalized_score || 0).toFixed(3)}^</span^>^</div^>^</div^>^<div^>#${index + 1} - v${image.version || '1.0'}^</div^>^</div^>`; >> temp_script.py
echo                 card.addEventListener('click', () =^> { >> temp_script.py
echo                     const modal = document.getElementById('modal'); >> temp_script.py
echo                     const modalImage = document.getElementById('modalImage'); >> temp_script.py
echo                     modalImage.src = imagePath; >> temp_script.py
echo                     modalImage.alt = imageName; >> temp_script.py
echo                     modal.style.display = 'block'; >> temp_script.py
echo                 }); >> temp_script.py
echo                 gallery.appendChild(card); >> temp_script.py
echo             }); >> temp_script.py
echo         } >> temp_script.py
echo         document.getElementById('sortMetric').addEventListener('change', (e) =^> { >> temp_script.py
echo             currentSort = e.target.value; >> temp_script.py
echo             renderGallery(); >> temp_script.py
echo         }); >> temp_script.py
echo         document.getElementById('sortOrder').addEventListener('change', (e) =^> { >> temp_script.py
echo             currentOrder = e.target.value; >> temp_script.py
echo             renderGallery(); >> temp_script.py
echo         }); >> temp_script.py
echo         document.getElementById('modal').addEventListener('click', () =^> { >> temp_script.py
echo             document.getElementById('modal').style.display = 'none'; >> temp_script.py
echo         }); >> temp_script.py
echo         document.querySelector('.close').addEventListener('click', () =^> { >> temp_script.py
echo             document.getElementById('modal').style.display = 'none'; >> temp_script.py
echo         }); >> temp_script.py
echo         document.addEventListener('DOMContentLoaded', () =^> { >> temp_script.py
echo             renderGallery(); >> temp_script.py
echo         }); >> temp_script.py
echo     ^</script^> >> temp_script.py
echo ^</body^> >> temp_script.py
echo ^</html^>""" >> temp_script.py
echo     with open(output_path, 'w', encoding='utf-8') as f: >> temp_script.py
echo         f.write(html_content) >> temp_script.py
echo     print(f"[OK] Generated HTML gallery: {output_path}") >> temp_script.py
echo     if image_data: >> temp_script.py
echo         scores = [img.get('summary', {}).get('advanced_scoring', {}).get('final_robust_score', 0) for img in image_data if img.get('summary', {}).get('advanced_scoring', {}).get('final_robust_score', 0) ^> 0] >> temp_script.py
echo         if scores: >> temp_script.py
echo             print(f"[STATS] {len(image_data)} images, avg: {sum(scores)/len(scores):.3f}, best: {max(scores):.3f}, worst: {min(scores):.3f}") >> temp_script.py
echo. >> temp_script.py
echo if __name__ == "__main__": >> temp_script.py
echo     main() >> temp_script.py

echo Running gallery generator...
python temp_script.py "%INPUT_FOLDER%"

REM Check if gallery was created successfully
if exist "%OUTPUT_FILE%" (
    echo.
    echo [SUCCESS] Gallery created successfully!
    echo Output file: %OUTPUT_FILE%
    echo.
    echo Opening gallery in your default web browser...
    start "" "%OUTPUT_FILE%"
    echo.
    echo Gallery opened! You can now browse your images with quality scores.
) else (
    echo.
    echo [ERROR] Failed to create gallery
    echo Please check that the folder contains JSON files with image data.
)

REM Clean up temporary file
if exist temp_script.py (
    del temp_script.py
)

echo.
echo Press any key to exit...
pause >nul
