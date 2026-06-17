import subprocess
import sys
import logging
from backend.sync import sync_from_excel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SEFIL_Pipeline")

def run_pipeline():
    scripts = ["Obtener_eventos_1.py", "Ordenar_eventos_2.py", "Generar_informe_3.py"]
    for script in scripts:
        logger.info(f"Ejecutando {script}...")
        result = subprocess.run([sys.executable, script], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            logger.error(f"Error ejecutando {script}:\n{result.stderr}")
            # If the biometric script times out, it's a known issue
            if "Obtener_eventos" in script and "timeout" in result.stderr.lower():
                return False, f"Error de conexión al biométrico (Timeout)."
            return False, f"Error en {script}."
        logger.info(f"{script} completado.")
    
    logger.info("Sincronizando a BD...")
    try:
        res = sync_from_excel("output_sefil/Reporte_SEFIL.xlsx")
        logger.info(f"Sync exitosa: {res}")
        return True, res
    except Exception as e:
        logger.error(f"Error en sync_from_excel: {e}")
        return False, str(e)

if __name__ == "__main__":
    success, result = run_pipeline()
    if not success:
        logger.error(result)
        sys.exit(1)
    logger.info("Pipeline completado exitosamente.")
