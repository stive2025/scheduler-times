import os

import requests
from requests.auth import HTTPDigestAuth
import pandas as pd
from datetime import datetime, timedelta
import urllib3
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings()

BASE_URL = os.getenv("BIOMETRIC_URL", "http://172.20.1.250")
USERNAME = os.getenv("BIOMETRIC_USER", "admin")
PASSWORD = os.getenv("BIOMETRIC_PASSWORD", "Sefil2026")

url = f"{BASE_URL}/ISAPI/AccessControl/AcsEvent?format=json"

try:
    from backend.database import SessionLocal, AttendanceDaily
    from sqlalchemy import func
    db = SessionLocal()
    max_date = db.query(func.max(AttendanceDaily.date)).scalar()
    db.close()
    if max_date:
        # Extraer desde 7 días antes de la última fecha sincronizada para cubrir cruces/fines de semana
        start_date_obj = max_date - timedelta(days=7)
        start_time = start_date_obj.strftime("%Y-%m-%dT00:00:00")
    else:
        # Base de datos vacía, extraer desde el inicio de los tiempos (o una fecha muy antigua)
        start_time = "2000-01-01T00:00:00"
except Exception as e:
    print(f"Advertencia: No se pudo conectar a BD para obtener última fecha ({e}). Usando default.")
    start_time = "2000-01-01T00:00:00"
end_time = datetime.now().strftime("%Y-%m-%dT23:59:59")

print(f"Consultando desde {start_time} hasta {end_time}...")

payload = {
    "AcsEventCond": {
        "searchID": "1",
        "searchResultPosition": 0,
        "maxResults": 30,
        "major": 5,
        "minor": 0,
        "startTime": start_time,
        "endTime": end_time,
        "timeReverseOrder": True
    }
}

# 🔥 Ajustado a tu equipo
VALID_MINORS = {75, 38, 1, 69}

def tipo_movimiento(door):
    if door == 1:
        return "Entrada"
    elif door == 2:
        return "Salida"
    return "Desconocido"

all_rows = []
position = 0

while True:
    payload["AcsEventCond"]["searchResultPosition"] = position

    try:
        response = requests.post(
            url,
            json=payload,
            auth=HTTPDigestAuth(USERNAME, PASSWORD),
            timeout=10
        )
    except Exception as e:
        print(f"Error en request: {e}")
        break

    data = response.json()
    eventos = data.get("AcsEvent", {}).get("InfoList", [])

    if not eventos:
        break

    print(f"Procesando {len(eventos)} eventos... (posición {position})")

    for ev in eventos:
        minor = ev.get("minor")
        door = ev.get("doorNo")

        # DEBUG útil
        #print(f"DEBUG: minor={minor}, door={door}")

        if minor not in VALID_MINORS:
            continue

        all_rows.append({
            "Empleado": ev.get("employeeNoString"),
            "Nombre": ev.get("name"),
            "Tarjeta": ev.get("cardNo"),
            "FechaHora": ev.get("time"),
            "Movimiento": tipo_movimiento(door),
            "Evento": f"Acceso válido ({minor})",
            "Puerta": door,
            "IP": ev.get("deviceIP"),
        })

    position += len(eventos)

# -----------------------------
# DATAFRAME
# -----------------------------
# DataFrame 
df = pd.DataFrame(all_rows) 

if df.empty:
    print("WARNING: No hay datos para exportar")
    exit()
# Limpiar timezone (IMPORTANTE) 
df["FechaHora"] = pd.to_datetime(df["FechaHora"], errors="coerce").dt.tz_localize(None) 
# Eliminar registros sin nombre 
df = df[df["Nombre"].notna() & (df["Nombre"].str.strip() != "")] 
#Ordenar 
df = df.sort_values(by="FechaHora") 
# Crear columna fecha (solo día) 
df["Fecha"] = df["FechaHora"].dt.date 
# Asignar Entrada/Salida por secuencia 
df["Movimiento"] = ( df.groupby(["Empleado", "Fecha"]) .cumcount() .apply(lambda x: "Entrada" if x % 2 == 0 else "Salida") ) 
#PRESENTACION
df_final = df[["Empleado", "Nombre", "FechaHora", "Movimiento"]].copy() 
# Separar 
df_final["Fecha"] = df_final["FechaHora"].dt.date 
df_final["Hora"] = df_final["FechaHora"].dt.time
df_final = df_final.drop(columns=["FechaHora"]) 
# Exportar 
df_final.to_excel("accesos_validos.xlsx", index=False)