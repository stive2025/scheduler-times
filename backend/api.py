import math
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd
from datetime import datetime
import subprocess
import sys
import os

import threading
import schedule
import time
from contextlib import asynccontextmanager

from backend.database import get_engine, SessionLocal
from backend.auth import authenticate_user, change_password, init_default_users
from backend.sync import get_last_sync, get_total_records
from backend.justifications import add_justification, remove_justification, list_justifications
from backend.schedules import get_all_employee_schedules, upsert_employee_schedule

def run_pipeline_job():
    print("Iniciando sincronización automática programada a las 22:00...", flush=True)
    subprocess.run([sys.executable, "main_pipeline.py"], capture_output=True)
    print("Sincronización automática completada.", flush=True)

def run_schedule_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    schedule.every().day.at("22:00").do(run_pipeline_job)
    thread = threading.Thread(target=run_schedule_loop, daemon=True)
    thread.start()
    yield
    schedule.clear()

app = FastAPI(title="Sefil Asistencias API", lifespan=lifespan)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev. In production restrict this.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize defaults
init_default_users()

# --- Helpers ---
DIAS_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",
           4:"Viernes",5:"Sábado",6:"Domingo"}

def _short_name(full_name):
    parts = str(full_name).strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return full_name

def _calc_olvido(row):
    return 1 if str(row['Evento']).strip() == 'Olvido' else 0

def _calc_estado(row):
    is_medio_tiempo = str(row.get('Evento', '')).strip() == 'Medio Tiempo'
    is_falta = str(row.get('Evento', '')).strip() == 'Falta'
    
    if row.get('total_atraso', 0) > 0:  
        return 'Con Atraso'
    if row.get('total_sal_ant', 0) > 0: 
        return 'Salida Anticipada'
    if row.get('olvidos', 0) > 0: 
        return 'Olvido'
    if is_falta: 
        return 'Falta'
    if is_medio_tiempo:
        if row.get('horas_trab', 0) >= 4:
            return 'Medio Tiempo'
    return 'A Tiempo'

def get_processed_data() -> pd.DataFrame:
    query = """
        SELECT 
            employee_id, employee_name, date, 
            schedule_name, shift_type, shift_detail, shift_str,
            entry_morning, exit_morning, entry_afternoon, exit_afternoon,
            hours_morning, hours_afternoon, hours_total,
            delay_morning_min, delay_afternoon_min, delay_total_min,
            early_exit_min, overtime_hours, event, annotations, month_period
        FROM attendance_daily
    """
    engine = get_engine()
    df = pd.read_sql(query, engine)
    
    if df.empty:
        return pd.DataFrame()

    df["Nombre"] = df["employee_name"]
    df["Fecha"] = pd.to_datetime(df["date"], errors="coerce")
    df["Horario Detectado"] = df["schedule_name"]
    df["Jornada"] = df["shift_type"]
    df["Entrada Mañana"] = df["entry_morning"]
    df["Salida Mañana"] = df["exit_morning"]
    df["Entrada Tarde"] = df["entry_afternoon"]
    df["Salida Tarde"] = df["exit_afternoon"]
    df["atr_man"] = df["delay_morning_min"].fillna(0).astype(float)
    df["atr_tar"] = df["delay_afternoon_min"].fillna(0).astype(float)
    df["total_atraso"] = df["delay_total_min"].fillna(0).astype(float)
    df["total_sal_ant"] = df["early_exit_min"].fillna(0).astype(float)
    df["horas_trab"] = df["hours_total"].fillna(0).astype(float)
    df["Evento"] = df["event"]

    df['dia_es'] = df['Fecha'].dt.dayofweek.map(DIAS_ES)
    df['mes'] = df['Fecha'].dt.strftime('%Y-%m')
    df['nom_corto'] = df['Nombre'].apply(_short_name)
    df['tiene_olvido'] = df.apply(_calc_olvido, axis=1)
    df['olvidos'] = df['tiene_olvido']
    df['estado'] = df.apply(_calc_estado, axis=1)

    return df

def clean_nan(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj

# --- API Models ---
class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordChangeRequest(BaseModel):
    username: str
    old_password: str
    new_password: str

class JustificationRequest(BaseModel):
    employee_id: str
    employee_name: str
    fecha: str
    tipo: str
    reason: str

class ScheduleRequest(BaseModel):
    employee_id: str
    employee_name: str
    schedule_name: str

class CalendarOverrideRequest(BaseModel):
    year: int
    month: int
    overrides: Dict[str, Dict[str, str]]

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str

class UserRoleUpdateRequest(BaseModel):
    role: str
    
# --- Endpoints ---

failed_login_attempts = {}

@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host
    now = time.time()
    
    # Rate Limiting check
    if client_ip in failed_login_attempts:
        attempts, lock_until = failed_login_attempts[client_ip]
        if lock_until and now < lock_until:
            raise HTTPException(status_code=429, detail="Demasiados intentos fallidos. Intente más tarde.")
        if lock_until and now >= lock_until:
            del failed_login_attempts[client_ip]

    result = authenticate_user(req.username, req.password)
    
    if result.get("status") == "ok":
        if client_ip in failed_login_attempts:
            del failed_login_attempts[client_ip]
        return {"success": True, "role": result.get("role"), "username": req.username}
        
    # Failed attempt
    attempts, _ = failed_login_attempts.get(client_ip, (0, None))
    attempts += 1
    if attempts >= 5:
        failed_login_attempts[client_ip] = (attempts, now + 300) # 5 mins block
    else:
        failed_login_attempts[client_ip] = (attempts, None)
        
    raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

@app.post("/api/auth/change-password")
def update_pwd(req: PasswordChangeRequest):
    success = change_password(req.username, req.old_password, req.new_password)
    if success.get("status") == "ok":
        return {"success": True}
    raise HTTPException(status_code=400, detail=success.get("message", "Contraseña actual incorrecta"))

from backend.auth import get_users, create_user, update_user_role, toggle_user_active

@app.get("/api/users")
def list_users(req: Request):
    return get_users()

@app.post("/api/users")
def add_user(req: UserCreateRequest):
    res = create_user(req.username, req.password, req.role)
    if res["status"] != "ok":
        raise HTTPException(status_code=400, detail=res["message"])
    return {"success": True}

@app.put("/api/users/{username}/role")
def edit_user_role(username: str, req: UserRoleUpdateRequest):
    res = update_user_role(username, req.role)
    if res["status"] != "ok":
        raise HTTPException(status_code=400, detail=res["message"])
    return {"success": True}

class UserStatusRequest(BaseModel):
    is_active: bool

@app.put("/api/users/{username}/status")
def edit_user_status(username: str, req: UserStatusRequest):
    res = toggle_user_active(username, req.is_active)
    if res["status"] != "ok":
        raise HTTPException(status_code=400, detail=res["message"])
    return {"success": True}

@app.get("/api/dashboard/data")
def get_dashboard_data():
    df = get_processed_data()
    if df.empty:
        return {"data": [], "months": [], "employees": [], "jornadas": []}
    
    # Sort and format for JSON
    df = df.sort_values(by=["date"], ascending=False)
    # Convert dates and times to string to prevent JSON serialization errors
    df["Fecha_str"] = df["Fecha"].dt.strftime("%Y-%m-%d")
    for col in ["Entrada Mañana", "Salida Mañana", "Entrada Tarde", "Salida Tarde"]:
        df[col] = df[col].astype(str).replace("None", "").replace("NaT", "")
        
    records = df.to_dict(orient="records")
    
    months = sorted(df["mes"].dropna().unique(), reverse=True)
    employees = sorted(df["nom_corto"].unique())
    jornadas = sorted(df["Jornada"].dropna().unique())
    
    return {
        "data": clean_nan(records),
        "months": months,
        "employees": employees,
        "jornadas": jornadas
    }

@app.get("/api/dashboard/kpis")
def get_kpis():
    df = get_processed_data()
    if df.empty:
        return {
            "n_emp": 0, "tot_h": 0, "tot_atr": 0, 
            "tot_sal": 0, "n_olv": 0, "pct_ok": 0
        }
        
    n_emp = df["Nombre"].nunique()
    tot_h = float(df["horas_trab"].sum())
    tot_atr = int(df["total_atraso"].sum())
    tot_sal = int(df["total_sal_ant"].sum())
    n_olv = int(df["tiene_olvido"].sum())
    pct_ok = float((df["estado"] == "A Tiempo").sum() / max(len(df), 1) * 100)
    
    return {
        "n_emp": n_emp,
        "tot_h": tot_h,
        "tot_atr": tot_atr,
        "tot_sal": tot_sal,
        "n_olv": n_olv,
        "pct_ok": pct_ok
    }

@app.get("/api/system/status")
def get_system_status():
    last_sync = get_last_sync()
    total_records = get_total_records()
    return {
        "last_sync": last_sync,
        "total_records": total_records
    }

@app.post("/api/system/sync")
def trigger_sync():
    try:
        # Run the pipeline script
        result = subprocess.run(
            [sys.executable, "main_pipeline.py"], 
            capture_output=True, 
            text=True
        )
        if result.returncode == 0:
            return {"success": True, "message": "Sincronización exitosa"}
        else:
            error_msg = (result.stderr or result.stdout or "Error desconocido")[-500:]
            raise HTTPException(status_code=500, detail=f"Error en pipeline: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/justifications")
def get_justifications(month: str = None):
    return list_justifications(month=month)

@app.post("/api/justifications")
def create_justification(req: JustificationRequest):
    res = add_justification(req.employee_id, req.employee_name, req.fecha, req.tipo, req.reason)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.delete("/api/justifications/{justif_id}")
def delete_justification(justif_id: int):
    res = remove_justification(justif_id)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    
    # Run sync to restore the original delays that were zeroed out
    import subprocess
    import sys
    subprocess.run([sys.executable, "main_pipeline.py"], capture_output=True)

    return res

@app.get("/api/schedules")
def get_schedules():
    from backend.schedules import get_all_employee_schedules
    df = get_processed_data()
    all_employees = []
    if not df.empty:
        emps = df[["employee_id", "Nombre"]].drop_duplicates().sort_values("Nombre")
        all_employees = emps.to_dict("records")
        
    configured = {s["employee_id"]: s["schedule_name"] for s in get_all_employee_schedules()}
    
    res = []
    for emp in all_employees:
        emp_id = str(emp["employee_id"])
        res.append({
            "employee_id": emp_id,
            "employee_name": emp["Nombre"],
            "schedule_name": configured.get(emp_id, "Automático")
        })
    return res

@app.post("/api/schedules")
def update_schedule(req: ScheduleRequest):
    res = upsert_employee_schedule(req.employee_id, req.employee_name, req.schedule_name)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.get("/api/calendar")
def get_calendar_matrix(year: int, month: int):
    import calendar as cal_mod
    from backend.calendar_override import get_manual_overrides
    df = get_processed_data()
    if df.empty:
        return {"data": [], "days_in_month": 0, "work_days": []}
        
    mask = (df["Fecha"].dt.year == year) & (df["Fecha"].dt.month == month)
    df_month = df[mask].copy()
    
    _, days_in_month = cal_mod.monthrange(year, month)
    all_days = [datetime(year, month, d).date() for d in range(1, days_in_month + 1)]
    has_sat_data = not df_month[df_month["Fecha"].dt.weekday == 5].empty
    work_days = [d.strftime("%d") for d in all_days if d.weekday() < 5 or (d.weekday() == 5 and has_sat_data)]
    non_work_days = [d for d in all_days if d.strftime("%d") not in work_days]
    
    # Building lookup
    def _map_evento_to_cal_state(evento: str, estado: str) -> str:
        ev = str(evento).strip()
        est = str(estado).strip()
        if ev in ("Permiso",): return "Permiso"
        if ev in ("Falta",) or est == "Falta":
            if ev == "Olvido": return "Asistencia"
            return "Falta"
        return "Asistencia"

    employees = df_month[["employee_id", "Nombre"]].drop_duplicates().sort_values("Nombre").reset_index(drop=True)
    lookup = {}
    for _, row in df_month.iterrows():
        key = (str(row["employee_id"]), row["Fecha"].date())
        estado = row.get("estado", "")
        lookup[key] = _map_evento_to_cal_state(row.get("Evento", ""), estado)
        
    # Manual overrides
    overrides = get_manual_overrides(year, month)
    for (emp_id, dt), status in overrides.items():
        lookup[(emp_id, dt)] = status
        
    # Pivot
    rows_data = []
    for _, emp in employees.iterrows():
        emp_id = str(emp["employee_id"])
        emp_name = emp["Nombre"]
        row_dict = {"employee_id": emp_id, "Empleado": emp_name}
        for d in all_days:
            day_key = d.strftime("%d")
            key = (emp_id, d)
            if d in non_work_days:
                row_dict[day_key] = lookup.get(key, "No Laborable")
            elif key in lookup:
                row_dict[day_key] = lookup[key]
            else:
                row_dict[day_key] = "Falta"
        rows_data.append(row_dict)
        
    return {
        "data": rows_data,
        "days_in_month": days_in_month,
        "work_days": work_days,
        "all_days": [d.strftime("%d") for d in all_days]
    }

@app.post("/api/calendar/override")
def save_calendar_override(req: CalendarOverrideRequest):
    from backend.calendar_override import save_manual_override
    # Since we can't easily parse row index in the backend without the exact same ordering,
    # we expect the frontend to pass the employee_id and date explicitly.
    # Actually, the Streamlit app used the row_index and dataframe order.
    # For this API, let's just make the frontend pass a list of {"employee_id", "date_str", "status"}
    pass # Wait, let me adjust the request model

class OverrideEntry(BaseModel):
    employee_id: str
    employee_name: str
    date_str: str # YYYY-MM-DD
    status: str

@app.post("/api/calendar/overrides")
def save_overrides(entries: List[OverrideEntry]):
    from backend.calendar_override import save_manual_override
    saved = 0
    for e in entries:
        dt = datetime.strptime(e.date_str, "%Y-%m-%d").date()
        res = save_manual_override(e.employee_id, e.employee_name, dt, e.status)
        if "error" not in res:
            saved += 1
    return {"saved": saved}
