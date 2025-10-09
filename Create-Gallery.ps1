# MUSIQ Image Gallery Generator
# Usage: .\Create-Gallery.ps1 "C:\Path\To\Your\Images"

param(
    [Parameter(Mandatory=$true)]
    [string]$InputFolder
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Image Quality Gallery Generator" -ForegroundColor Cyan
Write-Host " MUSIQ + VILA Multi-Model Scoring" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$OutputFile = Join-Path $InputFolder "gallery.html"

Write-Host "Input folder: $InputFolder" -ForegroundColor Yellow
Write-Host "Output file: $OutputFile" -ForegroundColor Yellow
Write-Host ""

# Check if input folder exists
if (-not (Test-Path $InputFolder)) {
    Write-Host "ERROR: Folder does not exist: $InputFolder" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Creating gallery for images in: $InputFolder" -ForegroundColor Green
Write-Host ""

Write-Host "Models used:" -ForegroundColor Cyan
Write-Host "  - MUSIQ models: SPAQ, AVA, KONIQ, PAQ2PIQ" -ForegroundColor White
Write-Host "  - VILA model: VILA (if Kaggle auth configured)" -ForegroundColor White
Write-Host ""

# Step 1: Run all models on all images in the folder
Write-Host "Step 1: Running image quality assessment..." -ForegroundColor Yellow
Write-Host "  - Processing with MUSIQ models (SPAQ, AVA, KONIQ, PAQ2PIQ)" -ForegroundColor White
Write-Host "  - Processing with VILA model (VILA)" -ForegroundColor White
Write-Host ""
Write-Host "Note: VILA models require Kaggle authentication." -ForegroundColor Cyan
Write-Host "If not configured, VILA will be skipped (MUSIQ will still work)." -ForegroundColor Cyan
Write-Host "See README_VILA.md for Kaggle setup instructions." -ForegroundColor Cyan
Write-Host ""
Write-Host "This may take a while depending on the number of images..." -ForegroundColor Yellow
Write-Host ""

# Check if we're in WSL environment or Windows
try {
    $wslCheck = Get-Command wsl -ErrorAction Stop
    Write-Host "Using WSL environment for multi-model processing..." -ForegroundColor Green
    
    # Convert Windows path to WSL path
    $wslPath = $InputFolder -replace '^([A-Z]):', '/mnt/$($matches[1].ToLower())' -replace '\\', '/'
    
    # Run batch processing in WSL
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '$wslPath' --output-dir '$wslPath'"
} catch {
    Write-Host "Using Windows Python environment for multi-model processing..." -ForegroundColor Green
    
    # Run batch processing in Windows
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    python "$ScriptDir\batch_process_images.py" --input-dir $InputFolder --output-dir $InputFolder
}

Write-Host ""
Write-Host "Step 2: Generating HTML gallery..." -ForegroundColor Yellow
Write-Host ""

# Create the Python script to generate the gallery
$PythonScript = @"
import os
import json
import glob
from pathlib import Path
from typing import List, Dict, Any

def load_json_data(directory: str) -> List[Dict[str, Any]]:
    """Load all JSON files and extract image data."""
    image_data = []
    
    # Find all JSON files
    json_pattern = os.path.join(directory, "*.json")
    json_files = glob.glob(json_pattern)
    
    print(f"Found {len(json_files)} JSON files")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Skip analysis and batch summary files
            filename = os.path.basename(json_file)
            if any(skip in filename.lower() for skip in ['analysis', 'batch_summary', 'weighted_scoring', 'cluster_summary', 'image_data', 'gallery']):
                continue
            
            # Ensure we have the required fields
            if 'image_path' in data and 'models' in data:
                # Convert paths to relative paths for web display
                image_path = data['image_path']
                if image_path.startswith('/mnt/d/'):
                    # Convert WSL path to Windows path for web access
                    image_path = image_path.replace('/mnt/d/', 'D:/')
                elif image_path.startswith('D:/'):
                    # Already Windows path
                    pass
                else:
                    # Make relative to the directory
                    image_path = os.path.basename(image_path)
                
                data['image_path'] = image_path
                image_data.append(data)
                
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    
    print(f"Loaded {len(image_data)} valid image records")
    return image_data

def generate_html_with_embedded_data(image_data: List[Dict[str, Any]], output_path: str):
    """Generate HTML file with embedded JSON data."""
    
    # Sort by final robust score (descending) by default
    image_data.sort(key=lambda x: x.get('summary', {}).get('advanced_scoring', {}).get('final_robust_score', 0), reverse=True)
    
    # Convert image data to JSON string
    json_data = json.dumps(image_data, indent=2, ensure_ascii=False)
    
    # HTML template
    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MUSIQ Image Quality Gallery</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
        }

        .header h1 {
            color: #333;
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header p {
            color: #666;
            font-size: 1.1em;
        }

        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .control-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
        }

        .control-group label {
            font-weight: 600;
            color: #333;
            font-size: 0.9em;
        }

        select {
            padding: 10px 15px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 1em;
            background: white;
            cursor: pointer;
            transition: all 0.3s ease;
            min-width: 200px;
        }

        select:hover {
            border-color: #667eea;
        }

        select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .stats {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .stat-item {
            text-align: center;
            padding: 15px 20px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border-radius: 15px;
            min-width: 120px;
        }

        .stat-number {
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .stat-label {
            font-size: 0.9em;
            opacity: 0.9;
        }

        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .image-card {
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .image-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
        }

        .image-container {
            position: relative;
            width: 100%;
            height: 200px;
            overflow: hidden;
        }

        .image-container img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.3s ease;
        }

        .image-card:hover .image-container img {
            transform: scale(1.05);
        }

        .image-info {
            padding: 15px;
        }

        .image-name {
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 0.9em;
            word-break: break-all;
        }

        .scores {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 10px;
        }

        .score-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 8px;
            background: #f8f9fa;
            border-radius: 8px;
            font-size: 0.8em;
        }

        .score-label {
            color: #666;
            font-weight: 500;
        }

        .score-value {
            font-weight: 600;
            color: #333;
        }

        .primary-score {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
        }

        .primary-score .score-label,
        .primary-score .score-value {
            color: white;
        }

        .metadata {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8em;
            color: #666;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }

        .loading {
            text-align: center;
            padding: 50px;
            color: #666;
            font-size: 1.2em;
        }

        .error {
            text-align: center;
            padding: 50px;
            color: #e74c3c;
            font-size: 1.2em;
        }

        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.9);
            cursor: pointer;
        }

        .modal-content {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            max-width: 90%;
            max-height: 90%;
        }

        .modal-content img {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }

        .close {
            position: absolute;
            top: 20px;
            right: 35px;
            color: #f1f1f1;
            font-size: 40px;
            font-weight: bold;
            cursor: pointer;
        }

        .close:hover {
            color: #bbb;
        }

        @media (max-width: 768px) {
            .gallery {
                grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                gap: 15px;
            }

            .controls {
                flex-direction: column;
                gap: 15px;
            }

            .stats {
                gap: 15px;
            }

            .header h1 {
                font-size: 2em;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎨 MUSIQ Image Quality Gallery</h1>
            <p>Browse your images sorted by different quality metrics</p>
        </div>

        <div class="controls">
            <div class="control-group">
                <label for="sortMetric">Sort by:</label>
                <select id="sortMetric">
                    <option value="final_robust_score">Final Robust Score</option>
                    <option value="weighted_score">Weighted Score</option>
                    <option value="median_score">Median Score</option>
                    <option value="average_normalized_score">Average Normalized</option>
                    <option value="spaq_score">SPAQ Score</option>
                    <option value="ava_score">AVA Score</option>
                    <option value="koniq_score">KONIQ Score</option>
                    <option value="paq2piq_score">PAQ2PIQ Score</option>
                    <option value="filename">Filename (A-Z)</option>
                    <option value="date">Date (Newest First)</option>
                </select>
            </div>
            <div class="control-group">
                <label for="sortOrder">Order:</label>
                <select id="sortOrder">
                    <option value="desc">Highest First</option>
                    <option value="asc">Lowest First</option>
                </select>
            </div>
        </div>

        <div class="stats" id="stats">
            <div class="stat-item">
                <div class="stat-number" id="totalImages">-</div>
                <div class="stat-label">Total Images</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" id="avgScore">-</div>
                <div class="stat-label">Avg Score</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" id="bestScore">-</div>
                <div class="stat-label">Best Score</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" id="worstScore">-</div>
                <div class="stat-label">Worst Score</div>
            </div>
        </div>

        <div id="gallery" class="gallery">
            <div class="loading">Loading images...</div>
        </div>
    </div>

    <!-- Modal for full-size image viewing -->
    <div id="modal" class="modal">
        <span class="close">&times;</span>
        <div class="modal-content">
            <img id="modalImage" src="" alt="">
        </div>
    </div>

    <script>
        // Embedded image data
        const imageData = {json_data};

        let currentSort = 'final_robust_score';
        let currentOrder = 'desc';

        // Update statistics
        function updateStats() {
            if (imageData.length === 0) return;

            const scores = imageData.map(img => getScore(img, currentSort)).filter(s => s !== null);
            
            document.getElementById('totalImages').textContent = imageData.length;
            document.getElementById('avgScore').textContent = scores.length > 0 ? 
                (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(3) : '-';
            document.getElementById('bestScore').textContent = scores.length > 0 ? 
                Math.max(...scores).toFixed(3) : '-';
            document.getElementById('worstScore').textContent = scores.length > 0 ? 
                Math.min(...scores).toFixed(3) : '-';
        }

        // Get score for sorting
        function getScore(image, metric) {
            switch (metric) {
                case 'final_robust_score':
                    return image.summary?.advanced_scoring?.final_robust_score || 
                           image.summary?.average_normalized_score || 0;
                case 'weighted_score':
                    return image.summary?.advanced_scoring?.weighted_score || 0;
                case 'median_score':
                    return image.summary?.advanced_scoring?.median_score || 0;
                case 'average_normalized_score':
                    return image.summary?.average_normalized_score || 0;
                case 'spaq_score':
                    return image.models?.spaq?.normalized_score || 0;
                case 'ava_score':
                    return image.models?.ava?.normalized_score || 0;
                case 'koniq_score':
                    return image.models?.koniq?.normalized_score || 0;
                case 'paq2piq_score':
                    return image.models?.paq2piq?.normalized_score || 0;
                case 'filename':
                    return image.image_name || '';
                case 'date':
                    return new Date(image.image_path || 0).getTime();
                default:
                    return 0;
            }
        }

        // Sort images
        function sortImages() {
            imageData.sort((a, b) => {
                const scoreA = getScore(a, currentSort);
                const scoreB = getScore(b, currentSort);
                
                if (currentSort === 'filename') {
                    return currentOrder === 'asc' ? 
                        scoreA.localeCompare(scoreB) : 
                        scoreB.localeCompare(scoreA);
                }
                
                if (currentOrder === 'asc') {
                    return scoreA - scoreB;
                } else {
                    return scoreB - scoreA;
                }
            });
        }

        // Render gallery
        function renderGallery() {
            sortImages();
            updateStats();
            
            const gallery = document.getElementById('gallery');
            gallery.innerHTML = '';

            imageData.forEach((image, index) => {
                const card = createImageCard(image, index);
                gallery.appendChild(card);
            });
        }

        // Create image card
        function createImageCard(image, index) {
            const card = document.createElement('div');
            card.className = 'image-card';
            
            const imageName = image.image_name || 'Unknown';
            const imagePath = image.image_path || '';
            const models = image.models || {};
            const summary = image.summary || {};
            const advanced = summary.advanced_scoring || {};
            
            // Get primary score based on current sort
            const primaryScore = getScore(image, currentSort);
            const primaryLabel = getScoreLabel(currentSort);
            
            card.innerHTML = `
                <div class="image-container">
                    <img src="${imagePath}" alt="${imageName}" loading="lazy" 
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIG5vdCBmb3VuZDwvdGV4dD48L3N2Zz4='">
                </div>
                <div class="image-info">
                    <div class="image-name">${imageName}</div>
                    <div class="scores">
                        <div class="score-item primary-score">
                            <span class="score-label">${primaryLabel}</span>
                            <span class="score-value">${primaryScore.toFixed(3)}</span>
                        </div>
                        <div class="score-item">
                            <span class="score-label">Avg</span>
                            <span class="score-value">${(summary.average_normalized_score || 0).toFixed(3)}</span>
                        </div>
                        <div class="score-item">
                            <span class="score-label">SPAQ</span>
                            <span class="score-value">${(models.spaq?.normalized_score || 0).toFixed(3)}</span>
                        </div>
                        <div class="score-item">
                            <span class="score-label">AVA</span>
                            <span class="score-value">${(models.ava?.normalized_score || 0).toFixed(3)}</span>
                        </div>
                        <div class="score-item">
                            <span class="score-label">KONIQ</span>
                            <span class="score-value">${(models.koniq?.normalized_score || 0).toFixed(3)}</span>
                        </div>
                        <div class="score-item">
                            <span class="score-label">PAQ2PIQ</span>
                            <span class="score-value">${(models.paq2piq?.normalized_score || 0).toFixed(3)}</span>
                        </div>
                    </div>
                    <div class="metadata">
                        <span>#${index + 1}</span>
                        <span>v${image.version || '1.0'}</span>
                    </div>
                </div>
            `;
            
            // Add click handler for modal
            card.addEventListener('click', () => {
                showModal(imagePath, imageName);
            });
            
            return card;
        }

        // Get score label
        function getScoreLabel(metric) {
            const labels = {
                'final_robust_score': 'Robust',
                'weighted_score': 'Weighted',
                'median_score': 'Median',
                'average_normalized_score': 'Average',
                'spaq_score': 'SPAQ',
                'ava_score': 'AVA',
                'koniq_score': 'KONIQ',
                'paq2piq_score': 'PAQ2PIQ',
                'filename': 'Name',
                'date': 'Date'
            };
            return labels[metric] || 'Score';
        }

        // Show modal
        function showModal(imagePath, imageName) {
            const modal = document.getElementById('modal');
            const modalImage = document.getElementById('modalImage');
            modalImage.src = imagePath;
            modalImage.alt = imageName;
            modal.style.display = 'block';
        }

        // Hide modal
        function hideModal() {
            document.getElementById('modal').style.display = 'none';
        }

        // Event listeners
        document.getElementById('sortMetric').addEventListener('change', (e) => {
            currentSort = e.target.value;
            renderGallery();
        });

        document.getElementById('sortOrder').addEventListener('change', (e) => {
            currentOrder = e.target.value;
            renderGallery();
        });

        // Modal event listeners
        document.getElementById('modal').addEventListener('click', hideModal);
        document.querySelector('.close').addEventListener('click', hideModal);

        // Initialize gallery when page loads
        document.addEventListener('DOMContentLoaded', () => {
            renderGallery();
        });
    </script>
</body>
</html>'''
    
    # Replace the placeholder with actual JSON data
    html_content = html_template.replace('{json_data}', json_data)
    
    # Write the HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Generated HTML gallery: {output_path}")

def main():
    """Main function."""
    import sys
    
    # Get directory from command line argument
    if len(sys.argv) < 2:
        print("Usage: python script.py <directory_path>")
        return
    
    directory = sys.argv[1]
    
    print(f"🔍 Loading image data from: {directory}")
    image_data = load_json_data(directory)
    
    if not image_data:
        print("No image data found!")
        return
    
    print(f"🎨 Generating HTML gallery...")
    output_path = os.path.join(directory, "gallery.html")
    generate_html_with_embedded_data(image_data, output_path)
    
    # Print some statistics
    if image_data:
        scores = []
        for img in image_data:
            score = img.get('summary', {}).get('advanced_scoring', {}).get('final_robust_score', 0)
            if score > 0:
                scores.append(score)
        
        if scores:
            print(f"\n📊 Gallery Statistics:")
            print(f"  Total images: {len(image_data)}")
            print(f"  Average score: {sum(scores)/len(scores):.3f}")
            print(f"  Best score: {max(scores):.3f}")
            print(f"  Worst score: {min(scores):.3f}")
            print(f"  Score range: {max(scores) - min(scores):.3f}")

if __name__ == "__main__":
    main()
"@

# Write the Python script to a temporary file
$PythonScript | Out-File -FilePath "temp_gallery_generator.py" -Encoding UTF8

Write-Host "Running gallery generator..." -ForegroundColor Green
python temp_gallery_generator.py $InputFolder

# Check if gallery was created successfully
if (Test-Path $OutputFile) {
    Write-Host ""
    Write-Host "✅ SUCCESS: Gallery created successfully!" -ForegroundColor Green
    Write-Host "📁 Output file: $OutputFile" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Gallery includes scores from:" -ForegroundColor Cyan
    Write-Host "  ✓ MUSIQ models (always included)" -ForegroundColor Green
    Write-Host "  ✓ VILA model (if Kaggle auth configured)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Opening gallery in your default web browser..." -ForegroundColor Green
    Start-Process $OutputFile
    Write-Host ""
    Write-Host "Gallery opened! You can now browse your images with quality scores." -ForegroundColor Green
    Write-Host "Images are sorted by weighted score from all available models." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "❌ ERROR: Failed to create gallery" -ForegroundColor Red
    Write-Host "Please check that the folder contains JSON files with image data." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If VILA models failed to load, check README_VILA.md for setup." -ForegroundColor Cyan
}

# Clean up temporary file
if (Test-Path "temp_gallery_generator.py") {
    Remove-Item "temp_gallery_generator.py"
}

Write-Host ""
Read-Host "Press Enter to exit"
