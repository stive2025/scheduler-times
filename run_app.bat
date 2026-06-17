@echo off
cd /d "%~dp0"
echo Iniciando SEFIL Asistencias...
echo ===================================

echo Iniciando Backend (FastAPI)...
start "Backend API" cmd /k "python -m uvicorn backend.api:app --port 8000"

echo Iniciando Frontend (React)...
start "Frontend Web" cmd /k "cd frontend && npm run dev"

echo.
echo Los servidores se estan iniciando en nuevas ventanas.
echo Cierra las ventanas emergentes para detener la aplicacion.
pause

