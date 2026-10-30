# Chạy web Catholic Near Me trên máy này: http://localhost:8000
# Chỉ nghe ở 127.0.0.1, máy khác trong mạng không truy cập được.
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

# Môi trường ảo: ưu tiên .venv ở thư mục gốc, nếu không có thì dùng chatbot\.venv (vị trí cũ).
$Python = @(".venv\Scripts\python.exe", "chatbot\.venv\Scripts\python.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) {
    Write-Error "Không tìm thấy môi trường ảo. Xem mục Cài đặt trong README.md."
    exit 1
}

if (-not (Test-Path "data\churches.db")) {
    & $Python scripts\build_db.py
}
& $Python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
