"""
Incremental sync from the SEFIL Excel report to PostgreSQL.

Reads the 'Detalle_Diario' sheet produced by Generar_informe_3.py and
upserts new records into the attendance_daily table.
"""

from __future__ import annotations

from datetime import datetime, time as dt_time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from .database import AttendanceDaily, SessionLocal, SyncLog

# ---------------------------------------------------------------------------
# Column mapping: cleaned Excel header → AttendanceDaily attribute
# ---------------------------------------------------------------------------
_COL_MAP = {
    "Empleado": "employee_id",
    "Nombre": "employee_name",
    "Fecha": "date",
    "Horario Detectado": "schedule_name",
    "Jornada": "shift_type",
    "Turno": "shift_detail",
    "Entrada Mañana": "entry_morning",
    "Salida Mañana": "exit_morning",
    "Entrada Tarde": "entry_afternoon",
    "Salida Tarde": "exit_afternoon",
    "Horas Mañana": "hours_morning",
    "Horas Tarde": "hours_afternoon",
    "Horas Total": "hours_total",
    "Atraso Man(min)": "delay_morning_min",
    "Atraso Tar(min)": "delay_afternoon_min",
    "Atraso Total(min)": "delay_total_min",
    "Salida Ant(min)": "early_exit_min",
    "Horas Extra": "overtime_hours",
    "Evento": "event",
}

# Columns that must be parsed as time objects
_TIME_COLS = {"entry_morning", "exit_morning", "entry_afternoon", "exit_afternoon"}

# Columns that must be parsed as Decimal / numeric
_NUMERIC_COLS = {
    "hours_morning",
    "hours_afternoon",
    "hours_total",
    "delay_morning_min",
    "delay_afternoon_min",
    "delay_total_min",
    "early_exit_min",
    "overtime_hours",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_time(value: Any) -> dt_time | None:
    """Convert a value to datetime.time or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dt_time):
        return value
    if isinstance(value, datetime):
        return value.time()
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _parse_numeric(value: Any) -> Decimal:
    """Convert a value to Decimal, defaulting to 0."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal("0")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------
def sync_from_excel(excel_path: Path | str) -> dict:
    """
    Incrementally sync the Excel report into PostgreSQL.

    Returns a dict with keys: added, skipped, date_start, date_end, status.
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        return {
            "added": 0,
            "skipped": 0,
            "date_start": None,
            "date_end": None,
            "status": f"error: file not found ({excel_path})",
        }

    # ------------------------------------------------------------------
    # 1. Read & clean the Excel sheet
    # ------------------------------------------------------------------
    df = pd.read_excel(excel_path, sheet_name="Detalle_Diario", header=1)

    # Clean column names: replace newlines, strip whitespace
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

    # Parse dates & drop rows without a valid date
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])

    if df.empty:
        return {
            "added": 0,
            "skipped": 0,
            "date_start": None,
            "date_end": None,
            "status": "warning: no valid rows found in Excel",
        }

    # ------------------------------------------------------------------
    # 2. Load existing records into a dictionary for quick lookup
    # ------------------------------------------------------------------
    session = SessionLocal()
    try:
        existing_records = {}
        for row in session.execute(select(AttendanceDaily)).scalars().all():
            existing_records[(row.employee_id, row.date)] = row

        added = 0
        updated = 0
        skipped = 0
        date_min = None
        date_max = None

        # ------------------------------------------------------------------
        # 3. Iterate rows and insert new records
        # ------------------------------------------------------------------
        for _, row in df.iterrows():
            emp_id = str(row.get("Empleado", "")).strip()
            fecha = row["Fecha"].date() if hasattr(row["Fecha"], "date") else row["Fecha"]

            # Track date range
            if date_min is None or fecha < date_min:
                date_min = fecha
            if date_max is None or fecha > date_max:
                date_max = fecha

            if (emp_id, fecha) in existing_records:
                # Update existing record
                record = existing_records[(emp_id, fecha)]
                record.employee_name = str(row.get("Nombre", "")).strip()
                record.schedule_name = _safe_str(row.get("Horario Detectado"))
                record.shift_type = _safe_str(row.get("Jornada"))
                record.shift_detail = _safe_str(row.get("Turno"))
                record.entry_morning = _parse_time(row.get("Entrada Mañana"))
                record.exit_morning = _parse_time(row.get("Salida Mañana"))
                record.entry_afternoon = _parse_time(row.get("Entrada Tarde"))
                record.exit_afternoon = _parse_time(row.get("Salida Tarde"))
                record.hours_morning = _parse_numeric(row.get("Horas Mañana"))
                record.hours_afternoon = _parse_numeric(row.get("Horas Tarde"))
                record.hours_total = _parse_numeric(row.get("Horas Total"))
                record.delay_morning_min = _parse_numeric(row.get("Atraso Man(min)"))
                record.delay_afternoon_min = _parse_numeric(row.get("Atraso Tar(min)"))
                record.delay_total_min = _parse_numeric(row.get("Atraso Total(min)"))
                record.early_exit_min = _parse_numeric(row.get("Salida Ant(min)"))
                record.overtime_hours = _parse_numeric(row.get("Horas Extra"))
                record.event = _safe_str(row.get("Evento"))
                record.month_period = fecha.strftime("%Y-%m")
                record.shift_str = _safe_str(row.get("Horario Detectado"))
                updated += 1
            else:
                # Build the ORM record
                record = AttendanceDaily(
                    employee_id=emp_id,
                    employee_name=str(row.get("Nombre", "")).strip(),
                    date=fecha,
                    schedule_name=_safe_str(row.get("Horario Detectado")),
                    shift_type=_safe_str(row.get("Jornada")),
                    shift_detail=_safe_str(row.get("Turno")),
                    entry_morning=_parse_time(row.get("Entrada Mañana")),
                    exit_morning=_parse_time(row.get("Salida Mañana")),
                    entry_afternoon=_parse_time(row.get("Entrada Tarde")),
                    exit_afternoon=_parse_time(row.get("Salida Tarde")),
                    hours_morning=_parse_numeric(row.get("Horas Mañana")),
                    hours_afternoon=_parse_numeric(row.get("Horas Tarde")),
                    hours_total=_parse_numeric(row.get("Horas Total")),
                    delay_morning_min=_parse_numeric(row.get("Atraso Man(min)")),
                    delay_afternoon_min=_parse_numeric(row.get("Atraso Tar(min)")),
                    delay_total_min=_parse_numeric(row.get("Atraso Total(min)")),
                    early_exit_min=_parse_numeric(row.get("Salida Ant(min)")),
                    overtime_hours=_parse_numeric(row.get("Horas Extra")),
                    event=_safe_str(row.get("Evento")),
                    month_period=fecha.strftime("%Y-%m"),
                )
                record.shift_str = _safe_str(row.get("Horario Detectado"))
                session.add(record)
                existing_records[(emp_id, fecha)] = record
                added += 1

        # ------------------------------------------------------------------
        # 4. Flush attendance records & log the sync
        # ------------------------------------------------------------------
        session.flush()

        log_entry = SyncLog(
            records_added=added,
            records_skipped=updated,
            date_range_start=date_min,
            date_range_end=date_max,
            source_file=str(excel_path),
            status="ok",
        )
        session.add(log_entry)
        session.commit()

        return {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "date_start": str(date_min) if date_min else None,
            "date_end": str(date_max) if date_max else None,
            "status": "ok",
        }

    except Exception as exc:
        session.rollback()
        return {
            "added": 0,
            "skipped": 0,
            "date_start": None,
            "date_end": None,
            "status": f"error: {exc}",
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Utility queries
# ---------------------------------------------------------------------------
def get_last_sync() -> dict | None:
    """Return info about the most recent sync, or None if no syncs exist."""
    session = SessionLocal()
    try:
        row = session.execute(
            select(SyncLog).order_by(SyncLog.synced_at.desc()).limit(1)
        ).scalar_one_or_none()

        if row is None:
            return None

        return {
            "id": row.id,
            "synced_at": str(row.synced_at),
            "records_added": row.records_added,
            "records_skipped": row.records_skipped,
            "date_range_start": str(row.date_range_start) if row.date_range_start else None,
            "date_range_end": str(row.date_range_end) if row.date_range_end else None,
            "source_file": row.source_file,
            "status": row.status,
        }
    finally:
        session.close()


def get_total_records() -> int:
    """Return the total count of records in attendance_daily."""
    session = SessionLocal()
    try:
        return session.execute(
            select(func.count(AttendanceDaily.id))
        ).scalar_one()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _safe_str(value: Any) -> str | None:
    """Convert to stripped string or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s else None
