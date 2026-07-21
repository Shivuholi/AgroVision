@echo off
title Reset Agrovision Database
color 0C

echo ==========================================
echo   WARNING: THIS WILL DELETE ALL LOG DATA
echo ==========================================
echo.
echo You recently upgraded the database schema (added the Lux column).
echo Running this script will safely delete the old database so the 
echo backend can automatically recreate the correct tables on its next run.
echo.

pause

cd /d "%~dp0\backend"
if exist "smart_agri.db" (
    del smart_agri.db
    echo Database deleted successfully!
) else (
    echo Database file not found. It might have already been deleted.
)

echo.
echo You can now run "run_agrovision.bat" to start the system.
pause
