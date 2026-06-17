@echo off
:: =====================================================================
:: SEFIL Attendance System - Manual and Scheduled Synchronization
:: =====================================================================

:: Ir al directorio donde se encuentra este archivo .bat
cd /d "%~dp0"

echo =====================================================================
echo    Sincronizador de Asistencia SEFIL (Extractor de biometrico)
echo =====================================================================
echo [1/3] Activando entorno virtual de Python...

if exist ".venv\Scripts\activate.bat" goto ACTIVATE_VENV
echo [ERROR] No se encontro la carpeta del entorno virtual (.venv).
echo Asegurate de estar en el directorio correcto y que .venv exista.
pause
exit /b 1

:ACTIVATE_VENV
call ".venv\Scripts\activate.bat"

echo [2/3] Ejecutando el pipeline de extraccion y procesamiento...
echo Esto consultara el dispositivo biometrico y actualizara la base de datos.
echo Rango maximo de consulta: hasta el dia de ayer a las 23:59:59.
echo.
python main_pipeline.py

if %errorlevel% equ 0 goto SYNC_SUCCESS
echo.
echo =====================================================================
echo [ERROR] Ocurrio un error al ejecutar el pipeline.
echo Verifica la conexion al biometrico (172.20.1.250) y que Docker este corriendo.
echo =====================================================================
goto END

:SYNC_SUCCESS
echo.
echo =====================================================================
echo [3/3] Sincronizacion completada exitosamente!
echo Los datos han sido actualizados en la base de datos de Docker.
echo Abre o actualiza el Dashboard para ver los resultados.
echo =====================================================================

:END
echo.
echo Presiona cualquier tecla para salir...
pause
exit /b 0
