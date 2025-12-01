# RESTORE SCRIPT - Run this to restore from backup
# Usage: .\restore_backup.ps1

$backupDir = "C:\TTS-main\backups\backup_20251129_171327"

Write-Host "Restoring from: $backupDir" -ForegroundColor Yellow
Write-Host ""

# Stop the server first
Write-Host "Stopping server..." -ForegroundColor Cyan
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Restore files
Write-Host "Restoring app.py..." -ForegroundColor Cyan
Copy-Item -Path "$backupDir\app.py" -Destination "C:\TTS-main\webapp\app.py" -Force

Write-Host "Restoring index.html..." -ForegroundColor Cyan
Copy-Item -Path "$backupDir\index.html" -Destination "C:\TTS-main\webapp\templates\index.html" -Force

Write-Host "Restoring ssml_builder.py..." -ForegroundColor Cyan
Copy-Item -Path "$backupDir\ssml_builder.py" -Destination "C:\TTS-main\webapp\ssml_builder.py" -Force

Write-Host "Restoring users.db..." -ForegroundColor Cyan
Copy-Item -Path "$backupDir\users.db" -Destination "C:\TTS-main\webapp\users.db" -Force

Write-Host ""
Write-Host "RESTORE COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "To restart the server, run:" -ForegroundColor Yellow
Write-Host "  cd C:\TTS-main\webapp" -ForegroundColor White
Write-Host "  C:\TTS-main\.venv\Scripts\python.exe app.py" -ForegroundColor White
