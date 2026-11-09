@echo off
title GMI FloorTakeoff Launcher - GMI Design and Implementation LLC
echo ========================================================
echo       GMI FloorTakeoff - Flooring & BOQ Takeoff
echo       GMI Design and Implementation LLC (Dubai, UAE)
echo ========================================================
echo.

echo [1/2] Starting Python FastAPI Backend on http://localhost:8000...
start "GMI Takeoff Backend (Port 8000)" cmd /k "cd /d %~dp0 && py run_local_backend.py"

echo [2/2] Starting React Frontend on http://localhost:5173...
start "GMI Takeoff Frontend (Port 5173)" cmd /k "cd /d %~dp0 && npm run dev"

echo.
echo ========================================================
echo  All systems running!
echo  Takeoff Frontend UI: http://localhost:5173
echo  Backend REST API:    http://localhost:8000
echo  Swagger API Docs:    http://localhost:8000/docs
echo ========================================================
echo.
pause
