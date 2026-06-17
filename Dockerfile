FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y forzar stdout a estar unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Configurar la zona horaria predeterminada (puede sobreescribirse en docker-compose)
ENV TZ=America/Guayaquil

WORKDIR /app

# Instalar dependencias del sistema (tzdata para la zona horaria)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

EXPOSE 8000

# Comando por defecto para el backend API
CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
