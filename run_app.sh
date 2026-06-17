#!/bin/bash
echo "Iniciando SEFIL Asistencias..."
echo "==================================="

# Navegar al directorio de este script
cd "$(dirname "$0")"

# Iniciar Backend en segundo plano
echo "Iniciando Backend (FastAPI)..."
python3 -m uvicorn backend.api:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Iniciar Frontend en segundo plano
echo "Iniciando Frontend (React)..."
cd frontend && npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

echo ""
echo "Los servidores se están ejecutando en segundo plano."
echo "Para detenerlos, presiona CTRL+C"

# Función para matar los procesos hijos si se cierra el script
cleanup() {
    echo "Deteniendo servidores..."
    kill $BACKEND_PID
    kill $FRONTEND_PID
    exit
}

trap cleanup SIGINT SIGTERM

# Mantener el script en ejecución
wait
