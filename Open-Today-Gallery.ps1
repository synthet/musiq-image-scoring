# Open Today's Photos Gallery
Write-Host "Opening Today's Photos Gallery..." -ForegroundColor Green
$galleryPath = "D:\Photos\Export\2025\2025-10-07\today_gallery.html"

if (Test-Path $galleryPath) {
    Start-Process $galleryPath
    Write-Host "Today's gallery opened in your default web browser." -ForegroundColor Green
} else {
    Write-Host "Gallery file not found: $galleryPath" -ForegroundColor Red
    Write-Host "Please run the organization script first." -ForegroundColor Yellow
}
