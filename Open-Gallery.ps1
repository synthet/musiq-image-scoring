# Open MUSIQ Image Quality Gallery
Write-Host "Opening MUSIQ Image Quality Gallery..." -ForegroundColor Green
$galleryPath = "D:\Photos\Export\2025\image_gallery_embedded.html"

if (Test-Path $galleryPath) {
    Start-Process $galleryPath
    Write-Host "Gallery opened in your default web browser." -ForegroundColor Green
} else {
    Write-Host "Error: Gallery file not found at $galleryPath" -ForegroundColor Red
}

Read-Host "Press Enter to continue"
