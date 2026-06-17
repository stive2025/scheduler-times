# Sistema de Control de Asistencias SEFIL (Versión Dockerizada + PostgreSQL)

Este proyecto implementa el sistema de control de asistencia para RRHH de SEFIL. Se compone de un panel interactivo desarrollado en **Streamlit** y una base de datos **PostgreSQL**.

---

## 🏛️ Arquitectura Híbrida (Opción A)

Dado que los contenedores de Docker ejecutados bajo WSL2 en Windows tienen limitaciones de enrutamiento para comunicarse de manera directa con dispositivos de la red local física (en este caso, el biométrico con IP `172.20.1.250`), este proyecto está configurado bajo la **Arquitectura Híbrida (Opción A)**:

1. **Dashboard y Base de Datos (en Docker):** 
   - El panel interactivo (Streamlit) y la base de datos PostgreSQL corren dentro de contenedores de Docker.
   - Esto asegura persistencia, portabilidad del dashboard y excelente velocidad de lectura para el frontend.
2. **Extractor de Datos (en Windows Host):**
   - El pipeline de Python (`main_pipeline.py`) que consulta el dispositivo biométrico y procesa los eventos se ejecuta **nativamente en Windows**.
   - Esto garantiza que el script siempre tenga acceso de red al biométrico `172.20.1.250`.
   - Una vez obtenidos los datos, el script se conecta al puerto de PostgreSQL expuesto en Windows (`localhost:5434`) e inserta los registros automáticamente en la base de datos de Docker.

---

## ⚙️ Requisitos Previos

Asegúrate de contar con lo siguiente instalado en tu máquina Windows:
1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) (con integración WSL2 activa).
2. [Python 3.11+](https://www.python.org/) instalado en Windows.
3. Un entorno virtual de Python configurado en la carpeta del proyecto. Si no existe, puedes crearlo e instalar dependencias con:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## 🚀 Guía de Puesta en Marcha

### Paso 1: Iniciar los Servicios de Docker
Abre tu terminal en la carpeta del proyecto y ejecuta:
```bash
docker compose up -d
```
Esto levantará dos contenedores:
* `sefil_postgres`: La base de datos PostgreSQL en el puerto `5434` (mapeado al host).
* `sefil_dashboard`: El panel Streamlit accesible en `http://localhost:8501`.

*Nota: La primera ejecución creará las tablas automáticamente mediante el archivo `db/init.sql`.*

### Paso 2: Sincronizar Datos desde el Biométrico
Para extraer los datos del biométrico local y cargarlos en la base de datos de Docker, tienes dos opciones:

#### Opción 2.1: Sincronización Manual (Doble clic)
1. Simplemente haz doble clic en el archivo **`sincronizar_asistencia.bat`** en la raíz del proyecto.
2. Se abrirá una ventana de consola que activará el entorno virtual `.venv`, ejecutará el pipeline de extracción y actualizará la base de datos.

#### Opción 2.2: Sincronización Automática (Programador de Tareas)
Para automatizar la sincronización todos los días a las **11:59 PM** (para obtener el día completo hasta ayer de manera segura):

1. Abre el **Programador de tareas de Windows** (escribe `Programador de tareas` en la barra de búsqueda de inicio).
2. En el panel derecho, haz clic en **Crear tarea básica...**.
3. **Nombre:** Escribe algo descriptivo, por ejemplo: `Sincronizador Asistencias SEFIL`. Haz clic en *Siguiente*.
4. **Desencadenador:** Selecciona **Diariamente** y haz clic en *Siguiente*.
5. **Hora de Inicio:** Configura la hora para las **23:59:00** (11:59 PM) y haz clic en *Siguiente*.
6. **Acción:** Selecciona **Iniciar un programa** y haz clic en *Siguiente*.
7. **Programa o script:** Haz clic en *Examinar* y selecciona el archivo **`sincronizar_asistencia.bat`** (ubicado en `C:\Users\Sistemas\Desktop\CASV_DOCS\Scripts\Asistencia\Asistencia\sincronizar_asistencia.bat`).
8. **Iniciar en (opcional):** **[CRÍTICO]** Debes escribir la ruta completa de la carpeta del proyecto:
   `C:\Users\Sistemas\Desktop\CASV_DOCS\Scripts\Asistencia\Asistencia`
   *(Si omites este paso, el script no encontrará el entorno virtual `.venv` ni los archivos Excel temporales).*
9. Haz clic en *Siguiente* y luego en *Finalizar*.

---

## 📊 Visualización del Dashboard

1. Abre tu navegador web e ingresa a: **`http://localhost:8501`**
2. Si acabas de ejecutar la sincronización manual desde Windows, presiona el botón **🔄 Sincronizar Datos** en la barra lateral del Dashboard. Esto limpiará la caché local de Streamlit y actualizará la vista con la nueva información agregada a la base de datos.
3. El panel ya no te pedirá subir archivos Excel, ya que carga todo el histórico de asistencias y justificaciones directamente desde la base de datos PostgreSQL de forma instantánea.

---

## 🛠️ Estructura del Proyecto

* `sincronizar_asistencia.bat`: Archivo ejecutable de automatización para Windows.
* `main_pipeline.py`: Orquestador que ejecuta la secuencia de extracción, ordenado, cálculo e inserción a BD.
* `Obtener_eventos_1.py`: Consulta al biométrico local usando credenciales del `.env`.
* `Ordenar_eventos_2.py` / `Generar_informe_3.py`: Procesan y generan los KPIs del día.
* `app_dashboard.py`: Código del panel visual Streamlit.
* `backend/`: Contiene la lógica interna de base de datos (`database.py`), sincronización incremental (`sync.py`) e inserción/eliminación de justificaciones (`justifications.py`).
* `.env`: Credenciales locales compartidas de la base de datos y biométrico.
