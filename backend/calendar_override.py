"""
Calendar override module for SEFIL attendance system.
Handles manual status assignments (Permiso, No Laborable, etc.)
via the interactive calendar in the Asistencias view.
"""

from datetime import datetime, date
from sqlalchemy import select, and_
from backend.database import SessionLocal, AttendanceDaily, ManualSchedule


def override_attendance_event(employee_id: str, str_date: str, new_status: str):
    """Legacy function: override the event field in attendance_daily."""
    session = SessionLocal()
    try:
        dt = datetime.strptime(str_date, '%d/%m/%Y').date()
        
        record = session.scalars(
            select(AttendanceDaily)
            .where(AttendanceDaily.employee_id == employee_id)
            .where(AttendanceDaily.date == dt)
        ).first()
        
        if record:
            record.event = new_status
        else:
            emp_name = session.scalars(
                select(AttendanceDaily.employee_name)
                .where(AttendanceDaily.employee_id == employee_id)
            ).first() or 'Desconocido'
            
            new_record = AttendanceDaily(
                employee_id=employee_id,
                employee_name=emp_name,
                date=dt,
                event=new_status,
                month_period=dt.strftime('%Y-%m'),
                schedule_name='Manual',
                shift_type='Manual'
            )
            session.add(new_record)
            
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def save_manual_override(employee_id: str, employee_name: str, dt: date, status: str):
    """
    Save a manual calendar override (Permiso, No Laborable, etc.)
    to the manual_schedules table. Uses UPSERT logic.
    """
    session = SessionLocal()
    try:
        # Check if override already exists
        existing = session.scalars(
            select(ManualSchedule)
            .where(
                and_(
                    ManualSchedule.employee_name == employee_name,
                    ManualSchedule.date == dt,
                )
            )
        ).first()

        if existing:
            existing.assigned_status = status
        else:
            new_override = ManualSchedule(
                employee_name=employee_name,
                date=dt,
                assigned_status=status,
            )
            session.add(new_override)

        # Also update the attendance_daily event if it's Permiso or Falta
        att_record = session.scalars(
            select(AttendanceDaily)
            .where(
                and_(
                    AttendanceDaily.employee_id == employee_id,
                    AttendanceDaily.date == dt,
                )
            )
        ).first()

        if status == "Permiso":
            if att_record:
                att_record.event = "Permiso"
            else:
                # Create a placeholder record for Permiso
                new_att = AttendanceDaily(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    date=dt,
                    event="Permiso",
                    month_period=dt.strftime('%Y-%m'),
                    schedule_name='Manual',
                    shift_type='Manual',
                )
                session.add(new_att)

        session.commit()
        return {"status": "ok"}
    except Exception as e:
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def get_manual_overrides(year: int, month: int) -> dict:
    """
    Retrieve all manual overrides for a given month.
    Returns dict of {(employee_id, date): status}.
    
    Since ManualSchedule uses employee_name (not employee_id),
    we join with attendance_daily to get the employee_id mapping.
    """
    session = SessionLocal()
    try:
        # Get all overrides for the month
        overrides = session.scalars(
            select(ManualSchedule)
            .where(ManualSchedule.date >= datetime(year, month, 1).date())
            .where(ManualSchedule.date < datetime(year + (1 if month == 12 else 0), 
                                                   (month % 12) + 1, 1).date())
        ).all()

        result = {}
        # Build name -> employee_id mapping from attendance_daily
        name_to_id = {}
        emp_rows = session.execute(
            select(AttendanceDaily.employee_name, AttendanceDaily.employee_id)
            .distinct()
        ).all()
        for name, eid in emp_rows:
            name_to_id[name] = str(eid)

        for ov in overrides:
            emp_id = name_to_id.get(ov.employee_name, ov.employee_name)
            result[(emp_id, ov.date)] = ov.assigned_status

        return result
    except Exception:
        return {}
    finally:
        session.close()


def save_manual_schedule(employee_name: str, dt: date, schedule: str):
    """
    Guarda un horario manual para un día específico (ej. "Horario C") en la tabla
    manual_schedules. Luego ejecuta el script Generar_informe_3.py y el sync
    para recalcular los atrasos automáticamente.
    """
    session = SessionLocal()
    try:
        # Check if override already exists
        existing = session.scalars(
            select(ManualSchedule)
            .where(
                and_(
                    ManualSchedule.employee_name == employee_name,
                    ManualSchedule.date == dt,
                )
            )
        ).first()

        if existing:
            existing.assigned_status = schedule
        else:
            new_override = ManualSchedule(
                employee_name=employee_name,
                date=dt,
                assigned_status=schedule,
            )
            session.add(new_override)

        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    # Disparar mini-pipeline (Paso 3 y Sync) de forma sincrona o en hilo separado
    # Lo ejecutamos sincrono porque dura ~5-10 segundos.
    import subprocess
    import sys
    from backend.sync import sync_from_excel
    import logging
    
    logger = logging.getLogger("SEFIL_CalendarOverride")
    
    try:
        logger.info("Ejecutando main_pipeline.py para recalcular horarios de manera completa...")
        result = subprocess.run([sys.executable, "main_pipeline.py"], capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            logger.error(f"Error en main_pipeline.py:\n{result.stderr}")
            return {"error": "Error al recalcular (main_pipeline)"}
            
        return {"status": "ok", "detail": "Pipeline completado."}
    except Exception as e:
        logger.error(f"Error en el mini-pipeline: {e}")
        return {"error": f"Error al sincronizar: {e}"}
