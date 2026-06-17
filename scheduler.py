import schedule
import time
import logging
from main_pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SEFIL_Scheduler")

def job():
    logger.info("Iniciando sincronización automática programada...")
    success, result = run_pipeline()
    if success:
        logger.info(f"Sincronización automática completada exitosamente: {result}")
    else:
        logger.error(f"Fallo en la sincronización automática: {result}")

# Ejecutar a las 23:59 todos los días
schedule.every().day.at("23:59").do(job)

if __name__ == "__main__":
    logger.info("Scheduler iniciado. Ejecutará el pipeline todos los días a las 23:59.")
    while True:
        schedule.run_pending()
        time.sleep(60)
