@echo off
REM ============================================================
REM Building Footprint Detection - Quick Start for Windows
REM ============================================================
REM This script starts all required services for the footprint detection workflow
REM 
REM WORKFLOW:
REM 1. Upload Old Image + New Image
REM 2. Auto Start Building Footprint Detection (Celery)
REM 3. Show Progress % in real-time
REM 4. Both Footprints Completed
REM 5. Enable "Start Upload" Button
REM 6. Run Change Detection
REM 7. Show Result
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║     Building Footprint Detection - Startup Manager             ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Check if Redis is installed
where redis-server >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Redis is not found in PATH
    echo.
    echo OPTION 1: Install Redis (Recommended for production)
    echo   - Download from: https://github.com/tporadowski/redis/releases
    echo   - Add to PATH or use absolute path
    echo.
    echo OPTION 2: Use memory broker (development mode)
    echo   - No Redis needed
    echo   - Tasks execute synchronously
    echo.
    set /p choice="Use memory broker? (y/n): "
    if /i "!choice!"=="y" (
        echo. & echo Using MEMORY BROKER (synchronous mode) & echo.
        set USE_MEMORY=1
    ) else (
        echo. & echo Please install Redis and add to PATH & echo.
        pause
        exit /b 1
    )
) else (
    echo ✓ Redis found
    echo.
    set USE_MEMORY=0
)

REM Create startup command window files
if %USE_MEMORY%==1 (
    echo Configuring for memory broker (development)...
    set CELERY_TASK_ALWAYS_EAGER=true
) else (
    echo Configuring for Redis broker (production)...
    set CELERY_TASK_ALWAYS_EAGER=false
)

REM Create Terminal 1 - Redis (if not using memory)
if %USE_MEMORY%==0 (
    echo Creating Terminal 1: Redis Server...
    powershell -NoExit -Command "Write-Host '═══════════════════════════════════════════' -ForegroundColor Cyan; Write-Host 'TERMINAL 1: Redis Server' -ForegroundColor Yellow; Write-Host '═══════════════════════════════════════════' -ForegroundColor Cyan; Write-Host 'Starting Redis...'; redis-server" > nul 2>&1 &
    timeout /t 2 /nobreak
)

REM Create Terminal 2 - Celery Worker
echo Creating Terminal 2: Celery Worker...
start cmd /k ^
    "cd /d %CD% && ^
    title Celery Worker && ^
    color 0A && ^
    echo. && ^
    echo ═══════════════════════════════════════════ && ^
    echo TERMINAL 2: Celery Worker && ^
    echo ═══════════════════════════════════════════ && ^
    echo. && ^
    call venv\Scripts\activate && ^
    echo Starting Celery worker... && ^
    echo. && ^
    celery -A my_gis_project worker --loglevel=info --reload"

timeout /t 3 /nobreak

REM Create Terminal 3 - Django Development Server
echo Creating Terminal 3: Django Server...
start cmd /k ^
    "cd /d %CD% && ^
    title Django Server && ^
    color 0B && ^
    echo. && ^
    echo ═══════════════════════════════════════════ && ^
    echo TERMINAL 3: Django Development Server && ^
    echo ═══════════════════════════════════════════ && ^
    echo. && ^
    call venv\Scripts\activate && ^
    python manage.py runserver"

REM Create Terminal 4 - Flower Dashboard (optional)
echo Creating Terminal 4: Flower Dashboard (Optional - Monitoring)...
start cmd /k ^
    "cd /d %CD% && ^
    title Flower Dashboard && ^
    color 0C && ^
    echo. && ^
    echo ═══════════════════════════════════════════ && ^
    echo TERMINAL 4: Flower Monitoring Dashboard && ^
    echo ═══════════════════════════════════════════ && ^
    echo. && ^
    call venv\Scripts\activate && ^
    pip install -q flower 2>nul && ^
    echo Starting Flower at http://localhost:5555 && ^
    echo. && ^
    celery -A my_gis_project flower"

REM Show main console
cls
color 0F
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║          FOOTPRINT DETECTION - ALL SERVICES STARTED            ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 WORKFLOW CHECKLIST:
echo.
echo  1️⃣  Navigate to: http://localhost:8000/upload/
echo  2️⃣  Upload OLD image (TIFF/JPG/PNG)
echo  3️⃣  Upload NEW image (TIFF/JPG/PNG)
echo  4️⃣  Watch Building Footprint Progress Trackers ⏳
echo  5️⃣  Wait for both to complete ✓
echo  6️⃣  "Start Upload" button enables
echo  7️⃣  Click "Start Upload" button
echo  8️⃣  View Change Detection Results
echo.
echo ─────────────────────────────────────────────────────────────────
echo 🌐 SERVICES RUNNING:
echo.
if %USE_MEMORY%==0 (
    echo   • Redis Server     → localhost:6379
    echo   • Celery Worker    → Running (check Terminal 2)
) else (
    echo   • Celery Worker    → Running (memory broker - Terminal 2)
)
echo   • Django Server    → http://localhost:8000
echo   • Flower Monitor   → http://localhost:5555 (Terminal 4)
echo.
echo ─────────────────────────────────────────────────────────────────
echo ⚙️  ENVIRONMENT:
echo.
if %USE_MEMORY%==0 (
    echo   Broker: Redis (async execution, real-time progress)
) else (
    echo   Broker: Memory (sync execution, progress after task)
)
echo.
echo ─────────────────────────────────────────────────────────────────
echo 🛑 TO STOP ALL SERVICES:
echo.
echo   1. Close each terminal window (Ctrl+C)
echo   2. Or run: taskkill /F /IM redis-server.exe (if using Redis)
echo.
echo ─────────────────────────────────────────────────────────────────
echo 📊 TROUBLESHOOTING:
echo.
echo   • Progress not updating? Check Celery Worker terminal (2)
echo   • Model not found? Verify ai_models/building_maskrcnn_trained.pth
echo   • Upload failing? Check Django Server terminal (3)
echo   • Redis error? Install from: github.com/tporadowski/redis/releases
echo.
echo ─────────────────────────────────────────────────────────────────
echo.
echo ✅ All services started! Check open terminals for logs.
echo.
pause
