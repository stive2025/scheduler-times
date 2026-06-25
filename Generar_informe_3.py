"""
=============================================================================
PROCESADOR DE ASISTENCIAS SEFIL — v3.0
=============================================================================
Genera reportes ejecutivos en Excel, Word y PDF a partir de:
  • reporte_asistencias.xlsx  — marcaciones diarias por empleado

El horario de cada registro se infiere automáticamente desde las
marcaciones (día de semana + pares de punches presentes):
  • Horario A       — Lun–Vie 08:00-13:00 / 14:00-17:00
  • Horario B       — Lun–Vie 09:30-14:00 / 15:00-18:30
  • Medio Tiempo    — Sólo mañana o tarde (mín. 4 h dentro de 08:00-18:30)
  • Especial        — Sábados 08:00-13:00

Instalación de dependencias:
    pip install pandas openpyxl python-docx reportlab

Para conversión Word → PDF en Windows/Mac:
    pip install docx2pdf
    (En Linux se usa LibreOffice si está disponible, sino reportlab)

Uso:
    python Generar_informe_3.py
=============================================================================
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
import os
import re
import sys

# Forzar UTF-8 en la salida para evitar errores con caracteres especiales en
# terminales Windows (cp1252) sin necesidad de PYTHONIOENCODING=utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import warnings
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    Alignment, Border, Font, GradientFill, PatternFill, Side
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

warnings.filterwarnings("ignore")

# ─── Configuración de rutas ───────────────────────────────────────────────────
BASE_DIR          = Path(__file__).parent
ARCHIVO_ASIST     = BASE_DIR / "reporte_asistencias.xlsx"
OUTPUT_DIR        = BASE_DIR / "output_sefil"
OUTPUT_DIR.mkdir(exist_ok=True)

OUT_EXCEL = OUTPUT_DIR / "Reporte_SEFIL.xlsx"
OUT_WORD  = OUTPUT_DIR / "Reporte_SEFIL.docx"
OUT_PDF   = OUTPUT_DIR / "Reporte_SEFIL.pdf"
OUT_IMGS  = OUTPUT_DIR  # imágenes se guardan aquí

# ─── Constantes de negocio ────────────────────────────────────────────────────
TOLERANCIA_MIN   = 10    # Minutos de gracia antes de marcar atraso
PAUSA_ALMUERZO_H = 1.5   # Horas de almuerzo estándar (referencia visual)

# ─── Horarios oficiales de la empresa ────────────────────────────────────────
# Cada horario define las horas esperadas que se usan para calcular atrasos
# y salidas anticipadas. El horario se detecta automáticamente por marcaciones.
HORARIOS_DEFINIDOS = {
    "A": {
        "nombre":      "Horario A",
        "jornada":     "Completa",
        "dias":        {0, 1, 2, 3, 4},   # Lunes–Viernes
        "entrada":     time(8,  0),
        "salida_man":  time(13, 0),
        "entrada_tar": time(14, 0),
        "salida":      time(17, 0),
        "turno_str":   "08:00-13:00 / 14:00-17:00",
    },
    "B": {
        "nombre":      "Horario B",
        "jornada":     "Completa",
        "dias":        {0, 1, 2, 3, 4},
        "entrada":     time(9,  30),
        "salida_man":  time(14, 0),
        "entrada_tar": time(15, 0),
        "salida":      time(18, 30),
        "turno_str":   "09:30-14:00 / 15:00-18:30",
    },
    "C": {
        "nombre":      "Horario C",
        "jornada":     "Completa",
        "dias":        {0, 1, 2, 3, 4},
        "entrada":     time(7,  0),
        "salida_man":  time(12, 0),
        "entrada_tar": time(13, 30),
        "salida":      time(16, 30),
        "turno_str":   "07:00-12:00 / 13:30-16:30",
    },
    "D": {
        "nombre":      "Horario D",
        "jornada":     "Completa",
        "dias":        {0, 1, 2, 3, 4},
        "entrada":     time(9,  0),
        "salida_man":  time(13, 30),
        "entrada_tar": time(13, 30),
        "salida":      time(15, 0),
        "turno_str":   "09:00-13:30 / 13:30-15:00",
    },
    "Especial": {
        "nombre":      "Horario Especial",
        "jornada":     "Especial",
        "dias":        {5},               # Sábado
        "entrada":     time(8,  0),
        "salida_man":  time(13, 0),
        "entrada_tar": None,
        "salida":      time(13, 0),
        "turno_str":   "08:00-13:00 (sábado)",
    },
}

HORAS_MIN_MEDIO_TIEMPO = 4.0
HORARIO_LABORAL_FIN    = time(18, 30)

# Paleta de colores corporativos (hex sin #)
COL = {
    "azul_oscuro":  "1F3864",
    "azul_medio":   "2E75B6",
    "azul_claro":   "D9E1F2",
    "naranja":      "ED7D31",
    "naranja_cl":   "FCE4D6",
    "verde":        "375623",
    "verde_cl":     "E2EFDA",
    "rojo_cl":      "FFE0E0",
    "gris_claro":   "F2F2F2",
    "blanco":       "FFFFFF",
}


# =============================================================================
# MÓDULO 1 — PARSEO DE HORAS + DETECCIÓN AUTOMÁTICA DE HORARIO
# =============================================================================

def _parse_hora(texto: str) -> time | None:
    """
    Convierte cadenas de hora a objeto time.
    Acepta: '8:30', '08:30', '9:30:00', '14:30'.
    Devuelve None si no puede parsear.
    """
    if not texto or pd.isna(texto):
        return None
    txt = str(texto).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(txt, fmt).time()
        except ValueError:
            continue
    return None


def inferir_horario(row: pd.Series, fixed_schedules: dict = None, manual_schedules: dict = None) -> tuple:
    """
    Determina el horario oficial para una fila de asistencia según:
      - Día de semana: sábado → Especial
      - Pares de marcaciones presentes: ambos (mañana+tarde) → Completa; uno solo → Media
      - Hora de entrada mañana: antes de 09:00 → Horario A; 09:00+ → Horario B
      - Medio Tiempo Tarde: entrada tarde antes de 15:00 → sub-tipo A; 15:00+ → sub-tipo B

    Devuelve 9 valores en este orden:
      Horario_Nombre, Jornada, Turno_Str,
      Hora_Entrada, Hora_Salida,
      Hora_Entrada_Man, Hora_Salida_Man,
      Hora_Entrada_Tar, Hora_Salida_Tar
    """
    fecha   = row["Fecha"]
    weekday = fecha.weekday() if pd.notna(fecha) else -1

    em = row["Entrada Mañana"]
    sm = row["Salida Mañana"]
    et = row["Entrada Tarde"]
    st = row["Salida Tarde"]

    tiene_man = em is not None or sm is not None
    tiene_tar = et is not None or st is not None

    # ── NUEVA LÓGICA: Bypasear inferencia si hay horario manual diario ──
    emp_name = str(row.get("Nombre", "")).strip()
    dt_val = row.get("Fecha")
    dt_key = dt_val.date() if pd.notna(dt_val) else None
    
    if "Cecibel" in emp_name and dt_key and dt_key.day == 24:
        print(f"DEBUG CECIBEL: emp_name={emp_name!r}, dt_key={dt_key!r}, in_manual={((emp_name, dt_key) in manual_schedules if manual_schedules else False)}")
    
    if manual_schedules and (emp_name, dt_key) in manual_schedules:
        manual_sched = manual_schedules[(emp_name, dt_key)]
        if manual_sched == "Medio Tiempo":
            if tiene_tar and not tiene_man:
                of_ent, of_sal = time(14, 0), time(17, 0)
                turno_s = "14:00-17:00 (medio tiempo tarde)"
                return ("Medio Tiempo", "Media", turno_s,
                        of_ent, of_sal, None, None, of_ent, of_sal)
            else:
                of_ent, of_sal = time(8, 0), time(12, 0)
                turno_s = "08:00-12:00 (medio tiempo mañana)"
                return ("Medio Tiempo", "Media", turno_s,
                        of_ent, of_sal, of_ent, of_sal, None, None)
        else:
            clave = manual_sched.replace("Horario ", "").strip()
            if clave in HORARIOS_DEFINIDOS:
                h = HORARIOS_DEFINIDOS[clave]
                return (h["nombre"], h["jornada"], h["turno_str"],
                        h["entrada"], h["salida"],
                        h["entrada"], h["salida_man"], h["entrada_tar"], h["salida"])

    # ── Bypasear inferencia si hay horario fijo configurado (Lunes a Viernes) ──
    emp_id = str(row.get("Empleado", "")).strip()
    if weekday >= 0 and weekday < 5 and fixed_schedules and emp_id in fixed_schedules:
        fixed_sched = fixed_schedules[emp_id]
        if fixed_sched == "Medio Tiempo":
            # Si tiene marcaciones en la tarde y no en la mañana, asumimos turno tarde, sino turno mañana
            if tiene_tar and not tiene_man:
                of_ent, of_sal = time(14, 0), time(17, 0)
                turno_s = "14:00-17:00 (medio tiempo tarde)"
                return ("Medio Tiempo", "Media", turno_s,
                        of_ent, of_sal, None, None, of_ent, of_sal)
            else:
                of_ent, of_sal = time(8, 0), time(12, 0)
                turno_s = "08:00-12:00 (medio tiempo mañana)"
                return ("Medio Tiempo", "Media", turno_s,
                        of_ent, of_sal, of_ent, of_sal, None, None)
        else:
            clave = fixed_sched.replace("Horario ", "").strip()
            if clave in HORARIOS_DEFINIDOS:
                h = HORARIOS_DEFINIDOS[clave]
                return (h["nombre"], h["jornada"], h["turno_str"],
                        h["entrada"], h["salida"],
                        h["entrada"], h["salida_man"], h["entrada_tar"], h["salida"])

    def _min(t):
        return t.hour * 60 + t.minute if t is not None else None

    # ── Sábado → Horario Especial ─────────────────────────────────────────
    if weekday == 5:
        h = HORARIOS_DEFINIDOS["Especial"]
        return (h["nombre"], h["jornada"], h["turno_str"],
                h["entrada"], h["salida"],
                h["entrada"], h["salida_man"], None, None)

    # ── Lunes–Viernes, marcaciones mañana Y tarde → Jornada Completa ─────
    if tiene_man and tiene_tar:
        entry_min = _min(em)
        if entry_min is not None:
            if entry_min < 7 * 60 + 30:
                clave = "C"
            elif entry_min < 8 * 60 + 30:
                clave = "A"
            elif entry_min < 9 * 60 + 15:
                clave = "D"
            else:
                clave = "B"
        else:
            # Fallback a deducción por salida
            sm_min = _min(sm)
            st_min = _min(st)
            if sm_min is not None:
                if sm_min < 12 * 60 + 30: clave = "C"
                elif sm_min < 13 * 60 + 15: clave = "A"
                elif sm_min < 13 * 60 + 45: clave = "D"
                else: clave = "B"
            elif st_min is not None:
                if st_min < 15 * 60 + 30: clave = "D"
                elif st_min < 16 * 60 + 45: clave = "C"
                elif st_min < 17 * 60 + 45: clave = "A"
                else: clave = "B"
            else:
                clave = "A"
        h = HORARIOS_DEFINIDOS[clave]
        return (h["nombre"], h["jornada"], h["turno_str"],
                h["entrada"], h["salida"],
                h["entrada"], h["salida_man"], h["entrada_tar"], h["salida"])

    # ── Sólo mañana → Medio Tiempo Mañana ────────────────────────────────
    if tiene_man and not tiene_tar:
        entry_min = _min(em)
        if entry_min is not None and entry_min >= 9 * 60:
            of_ent, of_sal = time(9, 30), time(13, 30)
            turno_s = "09:30-13:30 (medio tiempo mañana)"
        else:
            of_ent, of_sal = time(8, 0), time(12, 0)
            turno_s = "08:00-12:00 (medio tiempo mañana)"
        return ("Medio Tiempo", "Media", turno_s,
                of_ent, of_sal, of_ent, of_sal, None, None)

    # ── Sólo tarde → Medio Tiempo Tarde ──────────────────────────────────
    if tiene_tar and not tiene_man:
        entry_min = _min(et)
        if entry_min is not None and entry_min >= 15 * 60:
            of_ent, of_sal = time(15, 0), time(18, 30)
            turno_s = "15:00-18:30 (medio tiempo tarde)"
        else:
            of_ent, of_sal = time(14, 0), time(17, 0)
            turno_s = "14:00-17:00 (medio tiempo tarde)"
        return ("Medio Tiempo", "Media", turno_s,
                of_ent, of_sal, None, None, of_ent, of_sal)

    # ── Sin marcaciones ───────────────────────────────────────────────────
    return ("Sin datos", "Desconocido", "",
            None, None, None, None, None, None)


def inferir_y_asignar_horarios(df_asist: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica inferir_horario() a cada fila y adjunta las columnas de horario
    oficial al DataFrame de asistencias. Reemplaza la carga desde archivo.
    """
    print("  [2/5] Infiriendo horarios por marcaciones...")

    # Cargar horarios fijos y manuales diarios de la base de datos
    fixed_schedules = {}
    manual_schedules = {}
    try:
        from backend.database import SessionLocal, EmployeeSchedule, ManualSchedule
        from sqlalchemy import select
        session = SessionLocal()
        try:
            stmt = select(EmployeeSchedule)
            db_schedules = session.scalars(stmt).all()
            for s in db_schedules:
                if s.schedule_name and s.schedule_name != "Automático":
                    fixed_schedules[str(s.employee_id).strip()] = s.schedule_name
            if fixed_schedules:
                print(f"     → Cargados {len(fixed_schedules)} horarios fijos de empleados desde la BD.")
                
            stmt_manual = select(ManualSchedule).where(ManualSchedule.assigned_status.like('Horario%') | (ManualSchedule.assigned_status == 'Medio Tiempo'))
            db_manuals = session.scalars(stmt_manual).all()
            for m in db_manuals:
                manual_schedules[(m.employee_name, m.date)] = m.assigned_status
            if manual_schedules:
                print(f"     → Cargados {len(manual_schedules)} horarios manuales diarios desde la BD.")
        finally:
            session.close()
    except Exception as e:
        print(f"     ⚠️ Advertencia: No se pudieron cargar los horarios fijos de la BD ({e}). Se usará detección automática.")

    hor_cols = ["Horario_Nombre", "Jornada", "Turno_Str",
                "Hora_Entrada", "Hora_Salida",
                "Hora_Entrada_Man", "Hora_Salida_Man",
                "Hora_Entrada_Tar", "Hora_Salida_Tar"]

    inferidos = df_asist.apply(lambda r: inferir_horario(r, fixed_schedules, manual_schedules), axis=1, result_type="expand")
    inferidos.columns = hor_cols

    df_result = pd.concat(
        [df_asist.reset_index(drop=True), inferidos.reset_index(drop=True)],
        axis=1
    )

    # ── NUEVA LÓGICA: INFERENCIA SEMANAL ──
    # Extraemos semana y año
    df_result['ISO_Week'] = df_result['Fecha'].dt.isocalendar().week
    df_result['ISO_Year'] = df_result['Fecha'].dt.isocalendar().year

    # Buscamos el horario predominante por empleado en esa semana (sólo consideramos Horarios A, B, C, D)
    valid_mask = df_result['Horario_Nombre'].isin(['Horario A', 'Horario B', 'Horario C', 'Horario D'])
    weekly_modes = (
        df_result[valid_mask]
        .groupby(['Empleado', 'ISO_Year', 'ISO_Week'])['Horario_Nombre']
        .agg(lambda x: x.mode()[0] if not x.mode().empty else None)
        .reset_index(name='Horario_Semanal')
    )

    df_result = df_result.merge(weekly_modes, on=['Empleado', 'ISO_Year', 'ISO_Week'], how='left')

    # Reemplazamos el horario si es Lunes-Viernes y difiere del semanal
    mask_reemplazar = (
        (df_result['Fecha'].dt.weekday < 5) &
        df_result['Horario_Semanal'].notna() &
        (df_result['Horario_Nombre'] != df_result['Horario_Semanal'])
    )

    for idx in df_result[mask_reemplazar].index:
        emp_name = str(df_result.at[idx, 'Nombre']).strip()
        dt_val = df_result.at[idx, 'Fecha']
        dt_key = dt_val.date() if pd.notna(dt_val) else None
        
        # Evitar sobreescribir si este día fue asignado manualmente
        if manual_schedules and (emp_name, dt_key) in manual_schedules:
            continue
            
        nombre_horario = df_result.at[idx, 'Horario_Semanal']
        clave = nombre_horario.replace('Horario ', '')
        if clave in HORARIOS_DEFINIDOS:
            h = HORARIOS_DEFINIDOS[clave]
            df_result.at[idx, 'Horario_Nombre'] = h["nombre"]
            df_result.at[idx, 'Jornada'] = h["jornada"]
            df_result.at[idx, 'Turno_Str'] = h["turno_str"]
            df_result.at[idx, 'Hora_Entrada'] = h["entrada"]
            df_result.at[idx, 'Hora_Salida'] = h["salida"]
            df_result.at[idx, 'Hora_Entrada_Man'] = h["entrada"]
            df_result.at[idx, 'Hora_Salida_Man'] = h["salida_man"]
            df_result.at[idx, 'Hora_Entrada_Tar'] = h["entrada_tar"]
            df_result.at[idx, 'Hora_Salida_Tar'] = h["salida"]

    # Limpiar columnas temporales
    df_result = df_result.drop(columns=['ISO_Week', 'ISO_Year', 'Horario_Semanal'])

    dist = df_result["Horario_Nombre"].value_counts()
    print(f"     → {len(df_result)} registros procesados | Distribución detectada (post-ajuste semanal):")
    for nombre, cnt in dist.items():
        print(f"        {nombre}: {cnt} días")

    return df_result.reset_index(drop=True)


# =============================================================================
# MÓDULO 2 — CARGA DE ASISTENCIAS
# =============================================================================

def cargar_asistencias(filepath: Path) -> pd.DataFrame:
    """
    Lee reporte_asistencias.xlsx.
    Convierte columnas de hora de string 'HH:MM:SS' a objetos time.
    """
    print(f"  [1/5] Cargando asistencias: {filepath.name}")
    df = pd.read_excel(filepath)

    df["Empleado"] = df["Empleado"].astype(str).str.strip()
    df["Fecha"]    = pd.to_datetime(df["Fecha"], errors="coerce")

    # Columnas de hora → convertir de string a time
    for col in ["Entrada Mañana", "Salida Mañana", "Entrada Tarde", "Salida Tarde"]:
        df[col] = df[col].apply(_parse_hora)

    # Extraer mes para segmentación
    df["Mes"]        = df["Fecha"].dt.month
    df["Nombre_Mes"] = df["Fecha"].dt.strftime("%Y-%m")

    print(f"     → {len(df)} registros | "
          f"{df['Empleado'].nunique()} empleados | "
          f"Período: {df['Fecha'].min().date()} → {df['Fecha'].max().date()}")
    return df



# =============================================================================
# MÓDULO 4 — CÁLCULO DE KPIs
# =============================================================================

def _diff_minutos(t1: time | None, t2: time | None) -> float:
    """
    Calcula t2 - t1 en minutos.
    Devuelve 0.0 si alguno es None.
    """
    if t1 is None or t2 is None:
        return 0.0
    d = (t2.hour * 60 + t2.minute) - (t1.hour * 60 + t1.minute)
    return float(d)


def _atraso_con_tolerancia(real: time | None,
                            oficial: time | None,
                            tolerancia: int = TOLERANCIA_MIN) -> float:
    """
    Calcula minutos de atraso considerando tolerancia.
    Si real ≤ oficial + tolerancia → 0 (llegó a tiempo o dentro de gracia).
    Si real  > oficial + tolerancia → minutos de atraso desde la hora oficial.
    Devuelve 0 si cualquier valor es None.
    """
    if real is None or oficial is None:
        return 0.0
    real_min    = real.hour    * 60 + real.minute
    oficial_min = oficial.hour * 60 + oficial.minute
    limite      = oficial_min + tolerancia
    if real_min <= limite:
        return 0.0
    return float(real_min - limite)  # atraso descontando los 10 min de gracia


def _salida_anticipada(real: time | None, oficial: time | None) -> float:
    """
    Minutos de salida anticipada. > 0 si salió antes de la hora oficial.
    """
    if real is None or oficial is None:
        return 0.0
    real_min    = real.hour    * 60 + real.minute
    oficial_min = oficial.hour * 60 + oficial.minute
    return max(0.0, float(oficial_min - real_min))


def _horas_extra(real: time | None, oficial: time | None) -> float:
    """
    Minutos de tiempo extra (se quedó más allá de la hora oficial de salida).
    """
    if real is None or oficial is None:
        return 0.0
    real_min    = real.hour    * 60 + real.minute
    oficial_min = oficial.hour * 60 + oficial.minute
    return max(0.0, float(real_min - oficial_min))


def _determinar_turno_media(row: pd.Series) -> str:
    """
    Para empleados de Media Jornada, determina si el turno del día fue
    'mañana' o 'tarde' según qué marcaciones están presentes.
    """
    tiene_man = row["Entrada Mañana"] is not None or row["Salida Mañana"] is not None
    tiene_tar = row["Entrada Tarde"]  is not None or row["Salida Tarde"]  is not None
    if tiene_man and not tiene_tar:
        return "mañana"
    if tiene_tar and not tiene_man:
        return "tarde"
    if tiene_man and tiene_tar:
        return "mañana"   # ambos → tratar como mañana (caso raro/olvido)
    return "sin_datos"


def calcular_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula todas las métricas KPI registro por registro:
      - Horas trabajadas mañana y tarde (reales)
      - Horas trabajadas total
      - Minutos de atraso mañana / tarde / total (con tolerancia)
      - Minutos de salida anticipada
      - Minutos de tiempo extra
      - Clasificación del evento (Olvido, Completa, Medio tiempo, etc.)
    """
    print("  [3/5] Calculando KPIs...")

    resultados = []

    for _, row in df.iterrows():
        jornada = str(row.get("Jornada", "")).strip()
        anot    = str(row.get("Anotaciones", "")).strip()

        em_real = row["Entrada Mañana"]
        sm_real = row["Salida Mañana"]
        et_real = row["Entrada Tarde"]
        st_real = row["Salida Tarde"]

        # ── Horas trabajadas (reales) ─────────────────────────────────────
        h_man = max(0.0, _diff_minutos(em_real, sm_real)) / 60.0
        h_tar = max(0.0, _diff_minutos(et_real, st_real)) / 60.0
        h_tot = h_man + h_tar

        # ── Clasificación del evento ──────────────────────────────────────
        # Se extrae desde las Anotaciones originales del sistema
        if "olvido" in anot.lower() or "Olvido" in anot:
            evento = "Olvido"
        elif "medio tiempo" in anot.lower():
            # If the assigned schedule is full-time, missing a shift is an olvido
            if jornada == "Completa":
                evento = "Olvido"
            else:
                evento = "Medio Tiempo"
        elif "jornada completa" in anot.lower():
            evento = "Jornada Completa"
        elif "permiso" in anot.lower():
            evento = "Permiso"
        elif "falta" in anot.lower() and "olvido" not in anot.lower():
            evento = "Falta"
        else:
            evento = "Normal"

        # ── Lógica según tipo de jornada ──────────────────────────────────
        atr_man = 0.0
        atr_tar = 0.0
        sal_ant = 0.0
        h_extra = 0.0
        turno   = "N/A"

        if jornada == "Media":
            turno = _determinar_turno_media(row)

            if turno == "mañana":
                of_entrada = row["Hora_Entrada_Man"]
                of_salida  = row["Hora_Salida_Man"]
                atr_man    = _atraso_con_tolerancia(em_real, of_entrada)
                sal_ant    = _salida_anticipada(sm_real, of_salida)
                h_extra    = _horas_extra(sm_real, of_salida) / 60.0

            elif turno == "tarde":
                of_entrada = row["Hora_Entrada_Tar"]
                of_salida  = row["Hora_Salida_Tar"]
                atr_tar    = _atraso_con_tolerancia(et_real, of_entrada)
                sal_ant    = _salida_anticipada(st_real, of_salida)
                h_extra    = _horas_extra(st_real, of_salida) / 60.0

            # Lógica Medio Tiempo: Si completó al menos 4 horas en total, no hay atraso
            if h_tot >= HORAS_MIN_MEDIO_TIEMPO:
                atr_man = 0.0
                atr_tar = 0.0
                sal_ant = 0.0

        elif jornada == "Especial":
            # Sábado: solo marcaciones de mañana (entrada/salida mañana)
            of_ent_man = row["Hora_Entrada_Man"]   # 8:00
            of_sal_man = row["Hora_Salida_Man"]    # 13:00
            atr_man    = _atraso_con_tolerancia(em_real, of_ent_man)
            sal_ant    = _salida_anticipada(sm_real, of_sal_man)
            h_extra    = _horas_extra(sm_real, of_sal_man) / 60.0
            turno      = "especial"

        else:
            # ── Jornada Completa (Horario A u B) ─────────────────────────
            of_ent_man = row["Hora_Entrada_Man"]
            atr_man    = _atraso_con_tolerancia(em_real, of_ent_man)

            of_sal_tar = row["Hora_Salida_Tar"]
            sal_ant    = _salida_anticipada(st_real, of_sal_tar)
            h_extra    = _horas_extra(st_real, of_sal_tar) / 60.0

            turno = "completo"

        atr_tot = atr_man + atr_tar

        # ── Reclasificar Evento según Prioridad ───────────────────────────
        # Prioridad requerida: "A Tiempo" > "Atraso" > "Salida Anticipada" > "Olvido" > "Falta"
        # Primero, calculamos si existen estas condiciones en los KPIs:
        es_atraso = atr_tot > 0
        es_salida_ant = sal_ant > 0
        
        # Determine base event string based on conditions, only if it wasn't a justified type
        if evento not in ("Permiso", "Falta", "Medio Tiempo"):
            if evento == "Olvido":
                evento = "Olvido"
            elif es_atraso:
                evento = "Atraso"
            elif es_salida_ant:
                evento = "Salida Anticipada"
            else:
                evento = "A Tiempo"

        # Si había Falta pero hubo registro, debería ser algo diferente, pero ya se controla.

        resultados.append({
            # Identificación
            "Empleado":          row["Empleado"],
            "Nombre":            row["Nombre"],
            "Fecha":             row["Fecha"],
            "Mes":               row["Mes"],
            "Nombre_Mes":        row["Nombre_Mes"],
            # Marcaciones originales (para auditoría)
            "Entrada_Man_Real":  em_real,
            "Salida_Man_Real":   sm_real,
            "Entrada_Tar_Real":  et_real,
            "Salida_Tar_Real":   st_real,
            # Horario detectado
            "Horario_Nombre":    row.get("Horario_Nombre", ""),
            "Jornada":           jornada,
            "Turno":             turno,
            "Turno_Str":         row.get("Turno_Str", ""),
            # KPIs
            "Horas_Man":         round(h_man,  2),
            "Horas_Tar":         round(h_tar,  2),
            "Horas_Total":       round(h_tot,  2),
            "Atraso_Man_min":    round(atr_man, 2),
            "Atraso_Tar_min":    round(atr_tar, 2),
            "Atraso_Total_min":  round(atr_tot, 2),
            "Salida_Ant_min":    round(sal_ant, 2),
            "Horas_Extra":       round(h_extra, 2),
            # Clasificación
            "Evento":            evento,
            "Anotaciones":       anot,
        })

    df_kpi = pd.DataFrame(resultados)
    print(f"     → KPIs calculados para {len(df_kpi)} registros")
    return df_kpi


# =============================================================================
# MÓDULO 5 — GENERACIÓN DE RESÚMENES
# =============================================================================

def generar_resumen_general(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resumen agregado por empleado (todo el período).
    """
    agg = df.groupby(["Empleado", "Nombre", "Jornada"]).agg(
        Dias_Trabajados      = ("Fecha",          "count"),
        Horas_Total          = ("Horas_Total",    "sum"),
        Horas_Extra_Total    = ("Horas_Extra",    "sum"),
        Atraso_Total_min     = ("Atraso_Total_min","sum"),
        Salida_Ant_Total_min = ("Salida_Ant_min", "sum"),
        N_Olvidos            = ("Evento", lambda x: (x == "Olvido").sum()),
        N_Permisos           = ("Evento", lambda x: (x == "Permiso").sum()),
        N_Medio_Tiempo       = ("Evento", lambda x: (x == "Medio Tiempo").sum()),
        N_Jornada_Completa   = ("Evento", lambda x: (x == "Jornada Completa").sum()),
    ).reset_index()

    agg["Horas_Total"]          = agg["Horas_Total"].round(2)
    agg["Horas_Extra_Total"]    = agg["Horas_Extra_Total"].round(2)
    agg["Atraso_Total_min"]     = agg["Atraso_Total_min"].round(2)
    agg["Salida_Ant_Total_min"] = agg["Salida_Ant_Total_min"].round(2)

    # Promedio diario de atraso
    agg["Prom_Atraso_min"] = (
        agg["Atraso_Total_min"] / agg["Dias_Trabajados"]
    ).round(2)

    return agg.sort_values("Atraso_Total_min", ascending=False).reset_index(drop=True)


def generar_kpi_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """
    KPIs por empleado × mes. Se agrupa solo por Empleado+mes para evitar
    duplicados cuando el campo Nombre varía entre registros del mismo empleado.
    """
    nombre_map = df.groupby("Empleado")["Nombre"].first()

    agg = df.groupby(["Empleado", "Nombre_Mes", "Mes"]).agg(
        Dias_Trabajados      = ("Fecha",           "count"),
        Horas_Total          = ("Horas_Total",     "sum"),
        Horas_Extra          = ("Horas_Extra",     "sum"),
        Atraso_Total_min     = ("Atraso_Total_min","sum"),
        Atraso_Man_min       = ("Atraso_Man_min",  "sum"),
        Atraso_Tar_min       = ("Atraso_Tar_min",  "sum"),
        Salida_Ant_min       = ("Salida_Ant_min",  "sum"),
        N_Olvidos            = ("Evento", lambda x: (x == "Olvido").sum()),
        N_Permisos           = ("Evento", lambda x: (x == "Permiso").sum()),
    ).reset_index()

    agg.insert(1, "Nombre", agg["Empleado"].map(nombre_map))

    num_cols = ["Horas_Total","Horas_Extra","Atraso_Total_min",
                "Atraso_Man_min","Atraso_Tar_min","Salida_Ant_min"]
    for c in num_cols:
        agg[c] = agg[c].round(2)

    return agg.sort_values(["Nombre_Mes", "Nombre"]).reset_index(drop=True)


# =============================================================================
# MÓDULO 6 — EXPORTAR A EXCEL (3 pestañas con Tablas oficiales)
# =============================================================================

def _hex_fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)

def _border(style: str = "thin", color: str = "CCCCCC") -> Border:
    s = Side(style=style, color=color)
    return Border(left=s, right=s, top=s, bottom=s)

def _font(bold=False, size=10, color="000000", name="Arial") -> Font:
    return Font(bold=bold, size=size, color=color, name=name)

def _aln(h="center", v="center", wrap=False) -> Alignment:
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def _escribir_df_como_tabla(ws, df: pd.DataFrame,
                             nombre_tabla: str,
                             estilo_tabla: str,
                             fila_inicio: int = 1,
                             col_inicio:  int = 1,
                             col_headers: list[str] | None = None,
                             col_widths:  dict | None = None,
                             resaltar_col: str | None = None,
                             umbral_resalte: float = 0):
    """
    Escribe un DataFrame en una hoja de openpyxl y lo convierte en
    una Tabla oficial de Excel con filtros automáticos y estilo de filas alternas.
    """
    headers = col_headers if col_headers else list(df.columns)
    n_cols  = len(headers)
    n_filas = len(df)

    # ── Encabezado ────────────────────────────────────────────────────────
    for ci, h in enumerate(headers, col_inicio):
        cell = ws.cell(row=fila_inicio, column=ci, value=h)
        cell.font      = _font(bold=True, color="FFFFFF", size=10)
        cell.fill      = _hex_fill(COL["azul_oscuro"])
        cell.alignment = _aln("center", "center", wrap=True)
        cell.border    = _border("thin", "1F3864")
    ws.row_dimensions[fila_inicio].height = 28

    # ── Datos ─────────────────────────────────────────────────────────────
    idx_resalte = None
    if resaltar_col and resaltar_col in df.columns:
        idx_resalte = list(df.columns).index(resaltar_col)

    for ri, (_, row_data) in enumerate(df.iterrows()):
        row_excel = fila_inicio + 1 + ri
        fill_alt  = _hex_fill(COL["azul_claro"]) if ri % 2 == 0 else _hex_fill(COL["blanco"])

        for ci, col_name in enumerate(df.columns, col_inicio):
            val  = row_data[col_name]
            # Formatear times para visualización
            if isinstance(val, time):
                val = val.strftime("%H:%M:%S")
            elif pd.isna(val) if not isinstance(val, (str, time)) else False:
                val = ""

            cell = ws.cell(row=row_excel, column=ci, value=val)
            cell.font      = _font(size=9)
            cell.alignment = _aln("center", "center")
            cell.border    = _border("thin", "D9D9D9")

            # Color de fila alterna
            cell.fill = fill_alt

            # Resaltar valores altos (ej: mucho atraso → fondo naranja)
            if idx_resalte is not None and (ci - col_inicio) == idx_resalte:
                if isinstance(val, (int, float)) and val > umbral_resalte:
                    cell.fill = _hex_fill(COL["naranja_cl"])
                    cell.font = _font(bold=True, color="843C0C", size=9)

        ws.row_dimensions[row_excel].height = 16

    # ── Anchos de columna ─────────────────────────────────────────────────
    col_w_defaults = {h: max(len(h) + 2, 10) for h in headers}
    if col_widths:
        col_w_defaults.update(col_widths)
    for ci, h in enumerate(headers, col_inicio):
        ws.column_dimensions[get_column_letter(ci)].width = col_w_defaults.get(h, 12)

    # ── Tabla oficial de Excel ────────────────────────────────────────────
    fila_fin  = fila_inicio + n_filas
    col_fin_l = get_column_letter(col_inicio + n_cols - 1)
    col_ini_l = get_column_letter(col_inicio)
    ref       = f"{col_ini_l}{fila_inicio}:{col_fin_l}{fila_fin}"

    tabla = Table(displayName=nombre_tabla, ref=ref)
    tabla.tableStyleInfo = TableStyleInfo(
        name=estilo_tabla,
        showFirstColumn=False, showLastColumn=False,
        showRowStripes=True,   showColumnStripes=False
    )
    ws.add_table(tabla)
    return fila_fin


def exportar_excel(df_kpi: pd.DataFrame,
                   df_resumen: pd.DataFrame,
                   df_mensual: pd.DataFrame) -> Path:
    """
    Genera el archivo Excel con tres hojas formateadas como Tablas oficiales:
      1. Resumen_General
      2. KPI_Mensual
      3. Detalle_Diario
    """
    print("  [4a/5] Exportando Excel...")
    wb = Workbook()

    # ══════════════════════════════════════════════════════════════════════
    # HOJA 1 — Resumen General
    # ══════════════════════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title = "Resumen_General"
    ws1.sheet_view.showGridLines = False
    ws1.freeze_panes = "A2"

    # Título principal
    ws1.merge_cells("A1:M1")
    tc = ws1["A1"]
    tc.value     = "REPORTE DE ASISTENCIAS SEFIL — RESUMEN GENERAL"
    tc.font      = _font(bold=True, size=14, color="FFFFFF")
    tc.fill      = _hex_fill(COL["azul_oscuro"])
    tc.alignment = _aln("center", "center")
    ws1.row_dimensions[1].height = 32

    headers_res = ["Empleado", "Nombre", "Jornada", "Días\nTrabajados",
                   "Horas\nTotal", "Horas\nExtra", "Atraso\nTotal (min)",
                   "Salida Ant.\n(min)", "Prom. Atraso\n(min/día)",
                   "Olvidos", "Permisos", "J. Completa", "Medio Tiempo"]
    df_res_out = df_resumen[[
        "Empleado","Nombre","Jornada","Dias_Trabajados","Horas_Total",
        "Horas_Extra_Total","Atraso_Total_min","Salida_Ant_Total_min",
        "Prom_Atraso_min","N_Olvidos","N_Permisos",
        "N_Jornada_Completa","N_Medio_Tiempo"
    ]].copy()

    _escribir_df_como_tabla(
        ws1, df_res_out,
        nombre_tabla="Tabla_Resumen_General",
        estilo_tabla="TableStyleMedium9",
        fila_inicio=2,
        col_headers=headers_res,
        col_widths={"Nombre": 30, "Jornada": 12,
                    "Días\nTrabajados": 10, "Horas\nTotal": 10},
        resaltar_col="Atraso_Total_min",
        umbral_resalte=30,
    )

    # Nota al pie
    nota_row = len(df_res_out) + 4
    ws1.cell(row=nota_row, column=1,
             value=f"* Tolerancia de atraso: {TOLERANCIA_MIN} minutos").font = _font(
             size=8, color="666666")

    # ══════════════════════════════════════════════════════════════════════
    # HOJA 2 — KPI Mensual
    # ══════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("KPI_Mensual")
    ws2.sheet_view.showGridLines = False
    ws2.freeze_panes = "A2"

    ws2.merge_cells("A1:L1")
    tc2 = ws2["A1"]
    tc2.value     = "KPIs MENSUALES POR COLABORADOR"
    tc2.font      = _font(bold=True, size=13, color="FFFFFF")
    tc2.fill      = _hex_fill(COL["azul_medio"])
    tc2.alignment = _aln("center", "center")
    ws2.row_dimensions[1].height = 30

    headers_mes = ["Empleado", "Nombre", "Período", "Días\nTrabajados",
                   "Horas\nTotal", "Horas\nExtra", "Atraso\nTotal (min)",
                   "Atraso\nMañana (min)", "Atraso\nTarde (min)",
                   "Salida Ant.\n(min)", "Olvidos", "Permisos"]
    df_mes_out = df_mensual[[
        "Empleado","Nombre","Nombre_Mes","Dias_Trabajados","Horas_Total",
        "Horas_Extra","Atraso_Total_min","Atraso_Man_min","Atraso_Tar_min",
        "Salida_Ant_min","N_Olvidos","N_Permisos"
    ]].copy()

    _escribir_df_como_tabla(
        ws2, df_mes_out,
        nombre_tabla="Tabla_KPI_Mensual",
        estilo_tabla="TableStyleMedium2",
        fila_inicio=2,
        col_headers=headers_mes,
        col_widths={"Nombre": 28, "Período": 10},
        resaltar_col="Atraso_Total_min",
        umbral_resalte=20,
    )

    # ══════════════════════════════════════════════════════════════════════
    # HOJA 3 — Detalle Diario
    # ══════════════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("Detalle_Diario")
    ws3.sheet_view.showGridLines = False
    ws3.freeze_panes = "A2"

    ws3.merge_cells("A1:S1")
    tc3 = ws3["A1"]
    tc3.value     = "DETALLE DIARIO DE ASISTENCIAS"
    tc3.font      = _font(bold=True, size=13, color="FFFFFF")
    tc3.fill      = _hex_fill(COL["naranja"])
    tc3.alignment = _aln("center", "center")
    ws3.row_dimensions[1].height = 30

    headers_det = ["Empleado", "Nombre", "Fecha", "Horario\nDetectado", "Jornada", "Turno",
                   "Entrada\nMañana", "Salida\nMañana",
                   "Entrada\nTarde",  "Salida\nTarde",
                   "Horas\nMañana", "Horas\nTarde", "Horas\nTotal",
                   "Atraso\nMan(min)", "Atraso\nTar(min)", "Atraso\nTotal(min)",
                   "Salida\nAnt(min)", "Horas\nExtra", "Evento"]

    df_det_out = df_kpi[[
        "Empleado","Nombre","Fecha","Horario_Nombre","Jornada","Turno",
        "Entrada_Man_Real","Salida_Man_Real","Entrada_Tar_Real","Salida_Tar_Real",
        "Horas_Man","Horas_Tar","Horas_Total",
        "Atraso_Man_min","Atraso_Tar_min","Atraso_Total_min",
        "Salida_Ant_min","Horas_Extra","Evento"
    ]].copy()
    df_det_out["Fecha"] = df_det_out["Fecha"].dt.strftime("%Y-%m-%d")

    # Convertir times a string para la hoja Excel
    for c in ["Entrada_Man_Real","Salida_Man_Real","Entrada_Tar_Real","Salida_Tar_Real"]:
        df_det_out[c] = df_det_out[c].apply(
            lambda t: t.strftime("%H:%M:%S") if isinstance(t, time) else "")

    _escribir_df_como_tabla(
        ws3, df_det_out,
        nombre_tabla="Tabla_Detalle_Diario",
        estilo_tabla="TableStyleMedium7",
        fila_inicio=2,
        col_headers=headers_det,
        col_widths={"Nombre": 28, "Fecha": 12, "Evento": 16,
                    "Anotaciones": 30},
        resaltar_col="Atraso_Total_min",
        umbral_resalte=10,
    )

    wb.save(OUT_EXCEL)
    print(f"     → Excel guardado: {OUT_EXCEL}")
    return OUT_EXCEL


# =============================================================================
# MÓDULO 7 — EXPORTAR A WORD
# =============================================================================

def exportar_word(df_resumen: pd.DataFrame, df_mensual: pd.DataFrame) -> Path:
    """
    Genera informe ejecutivo en Word con tablas formateadas.
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    print("  [4b/5] Exportando Word...")
    doc = Document()

    # ── Márgenes y página ──────────────────────────────────────────────────
    sec = doc.sections[0]
    sec.page_width    = Cm(21.59)
    sec.page_height   = Cm(27.94)
    sec.left_margin   = sec.right_margin  = Cm(2.2)
    sec.top_margin    = sec.bottom_margin = Cm(1.8)

    def rgb(hex_color: str):
        r, g, b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
        return RGBColor(r, g, b)

    def set_cell_fill(cell, hex_color: str):
        """Aplica fondo a una celda de tabla."""
        tc = cell._tc
        tcp = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcp.append(shd)

    def titulo_word(text: str, nivel: int = 1, color_hex: str = "1F3864"):
        p = doc.add_heading(text, level=nivel)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for run in p.runs:
            run.font.color.rgb = rgb(color_hex)
        return p

    def agregar_fila_tabla(tabla, valores: list, bold=False, bg_hex: str | None = None,
                           font_size: int = 9):
        row = tabla.add_row()
        for i, val in enumerate(valores):
            cell = row.cells[i]
            cell.text = str(val)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.runs[0] if p.runs else p.add_run(str(val))
            run.font.size = Pt(font_size)
            run.font.bold = bold
            if bg_hex:
                set_cell_fill(cell, bg_hex)
        return row

    # ══════════════════════════════════════════════════════════════════════
    # PORTADA
    # ══════════════════════════════════════════════════════════════════════
    doc.add_paragraph()
    p_titulo = doc.add_paragraph()
    p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p_titulo.add_run("REPORTE EJECUTIVO DE ASISTENCIAS")
    r.font.size = Pt(22); r.font.bold = True; r.font.color.rgb = rgb(COL["azul_oscuro"])

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p_sub.add_run("SEFIL — Período: Enero–Marzo 2026")
    r2.font.size = Pt(13); r2.font.color.rgb = rgb(COL["azul_medio"])

    p_fecha = doc.add_paragraph()
    p_fecha.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = p_fecha.add_run(f"Generado el {datetime.now().strftime('%d de %B de %Y, %H:%M')}")
    r3.font.size = Pt(10); r3.font.color.rgb = rgb("888888")

    doc.add_paragraph()

    # Línea separadora visual (borde inferior)
    p_sep = doc.add_paragraph()
    p_sep.paragraph_format.space_after = Pt(12)
    p_border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"),   "single")
    bottom.set(qn("w:sz"),    "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), COL["azul_medio"])
    p_border.append(bottom)
    p_sep._p.get_or_add_pPr().append(p_border)

    # ══════════════════════════════════════════════════════════════════════
    # SECCIÓN 1 — Métricas globales
    # ══════════════════════════════════════════════════════════════════════
    titulo_word("1. Indicadores Generales del Período", nivel=1)

    total_empl   = len(df_resumen)
    total_horas  = df_resumen["Horas_Total"].sum()
    total_atraso = df_resumen["Atraso_Total_min"].sum()
    total_extra  = df_resumen["Horas_Extra_Total"].sum()
    total_olv    = df_resumen["N_Olvidos"].sum()

    metricas_glob = [
        ("Empleados evaluados",           str(total_empl)),
        ("Horas totales trabajadas",       f"{total_horas:.2f} h"),
        ("Horas extra totales",            f"{total_extra:.2f} h"),
        ("Minutos de atraso acumulados",   f"{total_atraso:.0f} min ({total_atraso/60:.1f} h)"),
        ("Olvidos de marcación",           str(int(total_olv))),
        ("Tolerancia de atraso aplicada",  f"{TOLERANCIA_MIN} minutos"),
    ]
    t_glob = doc.add_table(rows=1, cols=2)
    t_glob.style = "Table Grid"
    t_glob.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Encabezado
    enc = t_glob.rows[0].cells
    enc[0].text = "Indicador"; enc[1].text = "Valor"
    for cell in enc:
        set_cell_fill(cell, COL["azul_oscuro"])
        run = cell.paragraphs[0].runs[0]
        run.font.bold  = True
        run.font.size  = Pt(10)
        run.font.color.rgb = rgb("FFFFFF")
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, (ind, val) in enumerate(metricas_glob):
        bg = COL["azul_claro"] if i % 2 == 0 else COL["blanco"]
        agregar_fila_tabla(t_glob, [ind, val], bg_hex=bg, font_size=10)

    doc.add_paragraph()

    # ══════════════════════════════════════════════════════════════════════
    # SECCIÓN 2 — Tabla de Horas y Atrasos por Colaborador
    # ══════════════════════════════════════════════════════════════════════
    titulo_word("2. Horas Trabajadas y Atrasos por Colaborador", nivel=1)

    hdrs2 = ["Nombre", "Jornada", "Días\nTrab.", "Horas\nTotal",
             "Horas\nExtra", "Atraso\nTotal(min)", "Sal. Ant.\n(min)",
             "Olvidos", "Permisos"]
    n_cols2 = len(hdrs2)
    t2 = doc.add_table(rows=1, cols=n_cols2)
    t2.style  = "Table Grid"
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Encabezado
    for i, h in enumerate(hdrs2):
        cell = t2.rows[0].cells[i]
        cell.text = h
        set_cell_fill(cell, COL["azul_medio"])
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if p.runs:
            p.runs[0].font.bold  = True
            p.runs[0].font.size  = Pt(8)
            p.runs[0].font.color.rgb = rgb("FFFFFF")

    for i, (_, row) in enumerate(df_resumen.iterrows()):
        bg = COL["azul_claro"] if i % 2 == 0 else COL["blanco"]
        atraso = row["Atraso_Total_min"]
        bg_atr = COL["naranja_cl"] if atraso > 30 else bg
        vals = [
            row["Nombre"], row["Jornada"],
            int(row["Dias_Trabajados"]),
            f"{row['Horas_Total']:.2f}",
            f"{row['Horas_Extra_Total']:.2f}",
            f"{row['Atraso_Total_min']:.1f}",
            f"{row['Salida_Ant_Total_min']:.1f}",
            int(row["N_Olvidos"]),
            int(row["N_Permisos"]),
        ]
        row_w = t2.add_row()
        for j, val in enumerate(vals):
            cell = row_w.cells[j]
            cell.text = str(val)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_cell_fill(cell, bg_atr if j == 5 else bg)
            if p.runs:
                p.runs[0].font.size = Pt(8)

    doc.add_paragraph()
    nota = doc.add_paragraph(
        f"Nota: Las celdas en naranja indican atrasos superiores a 30 minutos. "
        f"Tolerancia aplicada: {TOLERANCIA_MIN} min.")
    nota.runs[0].font.size = Pt(8)
    nota.runs[0].font.color.rgb = rgb("666666")

    # ══════════════════════════════════════════════════════════════════════
    # SECCIÓN 3 — Resumen Mensual
    # ══════════════════════════════════════════════════════════════════════
    doc.add_page_break()
    titulo_word("3. Resumen de KPIs Mensual", nivel=1)

    hdrs3 = ["Nombre", "Período", "Días", "Horas\nTotal",
             "Atraso\nTotal(min)", "Atraso\nMan(min)",
             "Atraso\nTar(min)", "Olvidos", "Permisos"]
    t3 = doc.add_table(rows=1, cols=len(hdrs3))
    t3.style = "Table Grid"
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, h in enumerate(hdrs3):
        cell = t3.rows[0].cells[i]
        cell.text = h
        set_cell_fill(cell, COL["naranja"])
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if p.runs:
            p.runs[0].font.bold  = True
            p.runs[0].font.size  = Pt(8)
            p.runs[0].font.color.rgb = rgb("FFFFFF")

    for i, (_, row) in enumerate(df_mensual.iterrows()):
        bg = COL["naranja_cl"] if i % 2 == 0 else COL["blanco"]
        vals = [
            row["Nombre"], row["Nombre_Mes"],
            int(row["Dias_Trabajados"]),
            f"{row['Horas_Total']:.2f}",
            f"{row['Atraso_Total_min']:.1f}",
            f"{row['Atraso_Man_min']:.1f}",
            f"{row['Atraso_Tar_min']:.1f}",
            int(row["N_Olvidos"]),
            int(row["N_Permisos"]),
        ]
        row_w = t3.add_row()
        for j, val in enumerate(vals):
            cell = row_w.cells[j]
            cell.text = str(val)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_cell_fill(cell, bg)
            if p.runs:
                p.runs[0].font.size = Pt(8)

    # ══════════════════════════════════════════════════════════════════════
    # PIE DE DOCUMENTO
    # ══════════════════════════════════════════════════════════════════════
    doc.add_paragraph()
    p_pie = doc.add_paragraph()
    p_pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_pie = p_pie.add_run("Documento generado automáticamente — Uso interno y confidencial.")
    r_pie.font.size = Pt(8)
    r_pie.font.color.rgb = rgb("AAAAAA")

    doc.save(OUT_WORD)
    print(f"     → Word guardado: {OUT_WORD}")
    return OUT_WORD


# =============================================================================
# MÓDULO 8 — EXPORTAR A PDF (reportlab como motor primario / docx2pdf opcional)
# =============================================================================

def exportar_pdf_reportlab(df_resumen: pd.DataFrame,
                           df_mensual: pd.DataFrame) -> Path:
    """
    Genera el PDF con ReportLab (no requiere LibreOffice ni Word instalado).
    Para usar docx2pdf en su lugar, ver la función alternativa al final del módulo.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table as RLTable,
        TableStyle as RLTableStyle, HRFlowable, PageBreak, KeepTogether
    )

    print("  [4c/5] Exportando PDF con ReportLab...")

    C_AZ   = colors.HexColor("#1F3864")
    C_AZM  = colors.HexColor("#2E75B6")
    C_AZC  = colors.HexColor("#D9E1F2")
    C_NAR  = colors.HexColor("#ED7D31")
    C_NARC = colors.HexColor("#FCE4D6")
    C_GRIS = colors.HexColor("#F2F2F2")

    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=letter,
        leftMargin=0.85*inch, rightMargin=0.85*inch,
        topMargin=0.85*inch,  bottomMargin=0.85*inch,
    )

    st = getSampleStyleSheet()
    sty = {
        "titulo": ParagraphStyle("titulo", parent=st["Title"],
            textColor=C_AZ, fontSize=20, spaceAfter=4, alignment=TA_CENTER,
            fontName="Helvetica-Bold"),
        "subtit": ParagraphStyle("subtit", parent=st["Normal"],
            textColor=C_AZM, fontSize=12, alignment=TA_CENTER, spaceAfter=2),
        "fecha":  ParagraphStyle("fecha",  parent=st["Normal"],
            textColor=colors.grey, fontSize=9, alignment=TA_CENTER, spaceAfter=16),
        "h1":     ParagraphStyle("h1", parent=st["Heading1"],
            textColor=C_AZ, fontSize=13, fontName="Helvetica-Bold",
            spaceBefore=14, spaceAfter=6),
        "h2":     ParagraphStyle("h2", parent=st["Heading2"],
            textColor=C_AZM, fontSize=11, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=4),
        "normal": ParagraphStyle("normal2", parent=st["Normal"],
            fontSize=9, leading=13),
        "nota":   ParagraphStyle("nota", parent=st["Normal"],
            fontSize=7.5, textColor=colors.grey, alignment=TA_LEFT),
        "centro": ParagraphStyle("centro", parent=st["Normal"],
            fontSize=8, alignment=TA_CENTER, textColor=colors.grey),
    }

    def tabla_rl(datos, col_widths, style_extra=None):
        """Crea una tabla ReportLab con estilos base."""
        base_style = [
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 8),
            ("BACKGROUND",   (0,0), (-1,0), C_AZ),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
            ("ALIGN",        (0,0), (-1,-1), "CENTER"),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("LEFTPADDING",  (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("GRID",         (0,0), (-1,-1), 0.4, colors.lightgrey),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, C_GRIS]),
        ]
        if style_extra:
            base_style.extend(style_extra)
        t = RLTable(datos, colWidths=col_widths, repeatRows=1)
        t.setStyle(RLTableStyle(base_style))
        return t

    story = []

    # ── Portada ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4*inch))
    story.append(Paragraph("REPORTE EJECUTIVO DE ASISTENCIAS", sty["titulo"]))
    story.append(Paragraph("SEFIL — Período: Enero–Marzo 2026",  sty["subtit"]))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d de %B de %Y, %H:%M')}",
        sty["fecha"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_AZM, spaceAfter=16))

    # ── Métricas Globales ──────────────────────────────────────────────────
    story.append(Paragraph("1. Indicadores Generales del Período", sty["h1"]))

    total_empl   = len(df_resumen)
    total_horas  = df_resumen["Horas_Total"].sum()
    total_atraso = df_resumen["Atraso_Total_min"].sum()
    total_extra  = df_resumen["Horas_Extra_Total"].sum()
    total_olv    = df_resumen["N_Olvidos"].sum()

    glob_data = [
        ["Indicador", "Valor"],
        ["Empleados evaluados",           str(total_empl)],
        ["Horas totales trabajadas",       f"{total_horas:.2f} h"],
        ["Horas extra totales",            f"{total_extra:.2f} h"],
        ["Atraso acumulado",               f"{total_atraso:.0f} min  ({total_atraso/60:.1f} h)"],
        ["Olvidos de marcación (total)",   str(int(total_olv))],
        ["Tolerancia de atraso",           f"{TOLERANCIA_MIN} minutos"],
    ]
    story.append(tabla_rl(glob_data, [3.2*inch, 3.2*inch]))
    story.append(Spacer(1, 0.2*inch))

    # ── Tabla de Resumen por Colaborador ──────────────────────────────────
    story.append(Paragraph("2. Horas Trabajadas y Atrasos por Colaborador", sty["h1"]))

    hdrs_res = ["Nombre", "Jornada", "Días", "Horas\nTotal",
                "Horas\nExtra", "Atraso\nTotal(min)",
                "Sal.Ant\n(min)", "Olvidos"]
    res_data = [hdrs_res]
    extra_styles_res = []
    for i, (_, row) in enumerate(df_resumen.iterrows(), 1):
        res_data.append([
            row["Nombre"], row["Jornada"],
            int(row["Dias_Trabajados"]),
            f"{row['Horas_Total']:.2f}",
            f"{row['Horas_Extra_Total']:.2f}",
            f"{row['Atraso_Total_min']:.1f}",
            f"{row['Salida_Ant_Total_min']:.1f}",
            int(row["N_Olvidos"]),
        ])
        if row["Atraso_Total_min"] > 30:
            extra_styles_res.append(
                ("BACKGROUND", (5, i), (5, i), C_NARC)
            )

    widths_res = [2.1*inch, 0.9*inch, 0.5*inch, 0.8*inch,
                  0.8*inch, 1.0*inch, 0.8*inch, 0.6*inch]
    story.append(tabla_rl(res_data, widths_res, extra_styles_res))
    story.append(Paragraph(
        f"* Celdas naranja = atraso > 30 min | Tolerancia aplicada: {TOLERANCIA_MIN} min",
        sty["nota"]))
    story.append(Spacer(1, 0.2*inch))

    # ── KPIs Mensuales ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("3. KPIs Mensuales por Colaborador", sty["h1"]))

    hdrs_mes = ["Nombre", "Período", "Días", "Horas\nTotal",
                "Atraso\nTotal", "Atraso\nMañana", "Atraso\nTarde",
                "Olvidos", "Permisos"]
    mes_data = [hdrs_mes]
    for _, row in df_mensual.iterrows():
        mes_data.append([
            row["Nombre"], row["Nombre_Mes"],
            int(row["Dias_Trabajados"]),
            f"{row['Horas_Total']:.2f}",
            f"{row['Atraso_Total_min']:.1f}",
            f"{row['Atraso_Man_min']:.1f}",
            f"{row['Atraso_Tar_min']:.1f}",
            int(row["N_Olvidos"]),
            int(row["N_Permisos"]),
        ])

    widths_mes = [2.0*inch, 0.7*inch, 0.45*inch, 0.7*inch,
                  0.75*inch, 0.75*inch, 0.75*inch, 0.55*inch, 0.6*inch]
    story.append(tabla_rl(mes_data, widths_mes))

    # ── Pie de Página ─────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        "Documento generado automáticamente — Uso interno y confidencial.", sty["centro"]))

    doc.build(story)
    print(f"     → PDF guardado:   {OUT_PDF}")
    return OUT_PDF


def exportar_pdf_con_docx2pdf(word_path: Path) -> Path | None:
    """
    Alternativa: Convierte el Word a PDF usando docx2pdf.
    Requiere: pip install docx2pdf
    En Windows/Mac funciona directamente. En Linux necesita LibreOffice.
    """
    try:
        from docx2pdf import convert
        convert(str(word_path), str(OUT_PDF))
        print(f"     → PDF (docx2pdf) guardado: {OUT_PDF}")
        return OUT_PDF
    except ImportError:
        print("     ℹ  docx2pdf no instalado. Usando ReportLab como alternativa.")
        return None
    except Exception as e:
        print(f"     ⚠  docx2pdf falló ({e}). Usando ReportLab como alternativa.")
        return None



# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def main():
    print("\n" + "═"*65)
    print("   PROCESADOR DE ASISTENCIAS SEFIL — Iniciando pipeline")
    print("═"*65 + "\n")

    # ── Validar archivos de entrada ───────────────────────────────────────
    if not ARCHIVO_ASIST.exists():
        print(f"  ❌ Archivo no encontrado: {ARCHIVO_ASIST}")
        sys.exit(1)

    # ── Etapas del pipeline ───────────────────────────────────────────────
    df_asist = cargar_asistencias(ARCHIVO_ASIST)
    df_cruz  = inferir_y_asignar_horarios(df_asist)
    df_kpi   = calcular_kpis(df_cruz)

    df_resumen = generar_resumen_general(df_kpi)
    df_mensual = generar_kpi_mensual(df_kpi)

    print("\n  ── Generando archivos de salida ──────────────────────────────")

    # Excel
    exportar_excel(df_kpi, df_resumen, df_mensual)

    # Word
    word_path = exportar_word(df_resumen, df_mensual)

    # PDF — intentar docx2pdf primero, fallback a ReportLab
    pdf_path = exportar_pdf_con_docx2pdf(word_path)
    if pdf_path is None:
        pdf_path = exportar_pdf_reportlab(df_resumen, df_mensual)

    print("\n" + "═"*65)
    print("   ✅  PIPELINE COMPLETADO EXITOSAMENTE")
    print("═"*65)
    print(f"\n  📊  Excel     → {OUT_EXCEL.name}")
    print(f"  📝  Word      → {OUT_WORD.name}")
    print(f"  📄  PDF       → {OUT_PDF.name}")
    print(f"\n  Carpeta de salida: {OUTPUT_DIR}/")
    print(f"\n  Registros procesados : {len(df_kpi)}")
    print(f"  Empleados            : {df_kpi['Empleado'].nunique()}")
    print(f"  Meses cubiertos      : {df_kpi['Nombre_Mes'].nunique()}")
    print(f"  Total horas trabajadas: {df_kpi['Horas_Total'].sum():.2f} h")
    print(f"  Total atraso acumulado: {df_kpi['Atraso_Total_min'].sum():.1f} min")
    print("═"*65 + "\n")

    return df_kpi, df_resumen, df_mensual


if __name__ == "__main__":
    df_kpi, df_resumen, df_mensual = main()
