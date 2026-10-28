# Активация виртуального окружения
cd C:\Users\HP\vishap-7.0.1
& .\venv\Scripts\Activate.ps1

# Базовые переменные (dev-режим)
$env:VISHAP_DEV="true"
$env:STRIPE_SECRET_KEY="sk_test_dummy"
$env:CLERK_SECRET_KEY="sk_test_dummy"
$env:HARNESS_URL="http://127.0.0.1:3080"

# Включаем автозапуск DSH (Vishap сам его поднимет, если он выключен)

# Удаляем старые токены/куки из памяти, чтобы Vishap использовал встроенный поиск (pick_token)
Remove-Item Env:\HARNESS_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\HARNESS_COOKIE -ErrorAction SilentlyContinue

# Освобождаем порты (чтобы не было ошибки EADDRINUSE)
Write-Host "[+] Освобождаю порты 8080 и 3080..." -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 8080, 3080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# Запускаем API
Write-Host "[+] Запуск Vishap API..." -ForegroundColor Green
python -m src.main

# Пауза, чтобы окно не закрылось при ошибке
Write-Host "`nНажми Enter, чтобы закрыть окно..."
Read-Host