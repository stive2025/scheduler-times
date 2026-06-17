# Sistema de Control de Asistencias SEFIL

Este proyecto implementa el sistema de control de asistencia para RRHH de SEFIL. Se compone de un panel interactivo desarrollado en **React (Vite)**, una API en **FastAPI (Python)** y una base de datos **PostgreSQL**.

---

## 🏛️ Arquitectura del Sistema

La arquitectura está completamente contenerizada usando Docker Compose, lo que garantiza portabilidad y persistencia:

1. **Frontend (React + Vite):** Panel visual moderno, accesible en `http://localhost:8501`. Muestra métricas interactivas y tablas de datos.
2. **Backend (FastAPI):** API robusta accesible en el puerto `8000`. Sirve los datos al frontend y maneja las solicitudes de sincronización y modificaciones manuales.
3. **Base de Datos (PostgreSQL):** Almacena todo el historial de asistencias de forma segura, mapeado al puerto `5434` en el host.

---

## ⚙️ Requisitos Previos

Asegúrate de contar con lo siguiente instalado:
1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) (con integración WSL2 activa en Windows).
2. Git (opcional, para clonar el repositorio).

---

## 🚀 Guía de Puesta en Marcha

### Iniciar los Servicios
Abre tu terminal en la carpeta del proyecto y ejecuta:
```bash
docker compose up -d --build
```
Esto levantará los tres contenedores (`sefil_frontend`, `sefil_backend` y `sefil_postgres`).
*Nota: La primera ejecución creará las tablas automáticamente en la base de datos.*

---

## 🔄 Sincronización de Datos (Biométrico)

Para extraer los datos del biométrico y cargarlos en la base de datos, existen tres opciones:

#### Opción 1: Sincronización Manual (Desde la interfaz web)
1. Abre el Dashboard en `http://localhost:8501`.
2. Presiona el botón azul **"Forzar Sincronización DB"** en la esquina superior derecha.
3. El servidor backend se conectará al biométrico, procesará las asistencias del año en curso y actualizará la información automáticamente.

#### Opción 2: Sincronización Manual (Script Windows)
Puedes usar el script heredado haciendo doble clic en **`sincronizar_asistencia.bat`**. Este script activará el entorno virtual local de Python y ejecutará el pipeline.

#### Opción 3: Sincronización Automática (Programador de Tareas)
Para automatizar la sincronización todos los días a las **11:59 PM**:
1. Abre el **Programador de tareas de Windows**.
2. Haz clic en **Crear tarea básica...**.
3. Configura el **Desencadenador** diariamente a las **23:59:00**.
4. En **Acción**, selecciona **Iniciar un programa**.
5. Selecciona el archivo **`sincronizar_asistencia.bat`**.
6. **[CRÍTICO]** En **Iniciar en**, escribe la ruta completa de la carpeta del proyecto (ej. `C:\Users\...\Asistencia`).

---

## 📊 Visualización del Dashboard

1. Abre tu navegador web e ingresa a: **`http://localhost:8501`**
2. Interactúa con los filtros para ver el detalle por empleado, mes o jornada.
3. Los KPIs (Indicadores Clave) se actualizarán en tiempo real dependiendo de tus selecciones de filtro y gráficas.
4. El rol de RRHH (seleccionable en la esquina superior derecha) permite acceder a un botón adicional para realizar ajustes manuales directamente en la base de datos (e.g. convertir atrasos en justificados).

---

## 🛠️ Estructura del Proyecto

* `docker-compose.yml`: Orquestación de los contenedores Docker.
* `frontend/`: Código fuente de la interfaz de usuario en React y CSS vanilla.
* `backend/`: API en FastAPI (`app.py`, `api.py`), modelos SQLAlchemy (`models.py`) y manejo de base de datos (`database.py`).
* `main_pipeline.py`: Orquestador de Python que ejecuta la secuencia de extracción, cálculo de atrasos e inserción en base de datos.
* `Obtener_eventos_1.py`: Consulta al biométrico local usando credenciales del `.env`.
* `Ordenar_eventos_2.py`: Procesa las marcas crudas para identificar jornadas.
* `Generar_informe_3.py`: Genera los KPIs de atrasos, salidas anticipadas y reportes PDF/Excel.
* `sincronizar_asistencia.bat`: Archivo ejecutable opcional para Windows.
* `.env`: Credenciales locales de la base de datos y biométrico.
