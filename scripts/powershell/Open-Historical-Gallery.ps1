# Open Historical Photos Gallery
Write-Host "Opening Historical Photos Gallery..." -ForegroundColor Green
$galleryPath = "D:\Photos\Export\2025\historical_gallery.html"

if (Test-Path $galleryPath) {
    Start-Process $galleryPath
    Write-Host "Historical gallery opened in your default web browser." -ForegroundColor Green
} else {
    Write-Host "Gallery file not found: $galleryPath" -ForegroundColor Red
    Write-Host "Please run the regeneration script first." -ForegroundColor Yellow
}
