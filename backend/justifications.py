"""
CRUD operations for attendance justifications with auto-apply logic.

When a justification is added, the matching attendance_daily record is
automatically updated to zero-out the relevant delay / early-exit fields.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import AttendanceDaily, Justification, SessionLocal

# ---------------------------------------------------------------------------
# Valid justification types
# ---------------------------------------------------------------------------
VALID_TYPES = {"Atraso_Man", "Atraso_Tar", "Atraso", "Salida_Anticipada", "Todos"}


# ---------------------------------------------------------------------------
# Add justification
# ---------------------------------------------------------------------------
def add_justification(
    employee_id: str,
    employee_name: str,
    fecha: date | str,
    tipo: str,
    reason: str,
) -> dict:
    """
    Create a justification and auto-apply it to the matching attendance record.

    Returns a dict with 'status' ('ok' or 'error') and a descriptive 'message'.
    """
    # Validate type
    if tipo not in VALID_TYPES:
        return {
            "status": "error",
            "message": f"Tipo inválido '{tipo}'. Válidos: {', '.join(sorted(VALID_TYPES))}",
        }

    # Normalise date
    if isinstance(fecha, str):
        fecha = datetime.strptime(fecha, "%Y-%m-%d").date()

    session = SessionLocal()
    try:
        if employee_id == "TODOS":
            attendances = session.execute(
                select(AttendanceDaily).where(AttendanceDaily.date == fecha)
            ).scalars().all()
            
            count = 0
            for attendance in attendances:
                existing = session.execute(
                    select(Justification).where(
                        Justification.employee_id == attendance.employee_id,
                        Justification.date == fecha,
                        Justification.type == tipo,
                    )
                ).scalar_one_or_none()
                
                if existing is None:
                    justif = Justification(
                        employee_id=attendance.employee_id,
                        employee_name=attendance.employee_name,
                        date=fecha,
                        type=tipo,
                        reason=reason,
                        applied=True,
                    )
                    session.add(justif)
                    _apply_justification(attendance, tipo)
                    count += 1
            
            session.commit()
            return {
                "status": "ok",
                "message": f"Justificación grupal aplicada a {count} empleados.",
            }

        # Check for duplicate
        existing = session.execute(
            select(Justification).where(
                Justification.employee_id == employee_id,
                Justification.date == fecha,
                Justification.type == tipo,
            )
        ).scalar_one_or_none()

        if existing is not None:
            return {
                "status": "error",
                "message": (
                    f"Ya existe una justificación de tipo '{tipo}' para "
                    f"empleado {employee_id} en fecha {fecha}."
                ),
            }

        # Insert justification
        justif = Justification(
            employee_id=employee_id,
            employee_name=employee_name,
            date=fecha,
            type=tipo,
            reason=reason,
            applied=False,
        )
        session.add(justif)
        session.flush()  # get the id

        # Find matching attendance record
        attendance = session.execute(
            select(AttendanceDaily).where(
                AttendanceDaily.employee_id == employee_id,
                AttendanceDaily.date == fecha,
            )
        ).scalar_one_or_none()

        if attendance is not None:
            _apply_justification(attendance, tipo)
            justif.applied = True
        else:
            justif.applied = False

        session.commit()

        return {
            "status": "ok",
            "message": (
                f"Justificación creada (id={justif.id}). "
                + ("Aplicada al registro de asistencia." if justif.applied else
                   "No se encontró registro de asistencia para aplicar.")
            ),
            "justification_id": justif.id,
            "applied": justif.applied,
        }

    except IntegrityError:
        session.rollback()
        return {
            "status": "error",
            "message": "Error de integridad: posible duplicado.",
        }
    except Exception as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Remove justification
# ---------------------------------------------------------------------------
def remove_justification(justif_id: int) -> dict:
    """Delete a justification by its primary key."""
    session = SessionLocal()
    try:
        justif = session.get(Justification, justif_id)
        if justif is None:
            return {
                "status": "error",
                "message": f"Justificación con id={justif_id} no encontrada.",
            }

        session.delete(justif)
        session.commit()

        return {
            "status": "ok",
            "message": f"Justificación id={justif_id} eliminada.",
        }
    except Exception as exc:
        session.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# List justifications
# ---------------------------------------------------------------------------
def list_justifications(
    month: str | None = None,
    employee_id: str | None = None,
) -> list[dict]:
    """
    Return justifications filtered by month ('YYYY-MM') and/or employee_id.
    Ordered by date descending.
    """
    session = SessionLocal()
    try:
        stmt = select(Justification)

        if month:
            # month format: '2026-01'
            try:
                year, mon = month.split("-")
                start = date(int(year), int(mon), 1)
                if int(mon) == 12:
                    end = date(int(year) + 1, 1, 1)
                else:
                    end = date(int(year), int(mon) + 1, 1)
                stmt = stmt.where(
                    Justification.date >= start,
                    Justification.date < end,
                )
            except (ValueError, TypeError):
                pass  # ignore malformed month, return unfiltered

        if employee_id:
            stmt = stmt.where(Justification.employee_id == employee_id)

        stmt = stmt.order_by(Justification.date.desc())

        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_name": r.employee_name,
                "date": str(r.date),
                "type": r.type,
                "reason": r.reason,
                "applied": r.applied,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Internal: apply justification to attendance
# ---------------------------------------------------------------------------
def _apply_justification(attendance: AttendanceDaily, tipo: str) -> None:
    """
    Zero-out the appropriate delay / early-exit fields on an AttendanceDaily
    record based on the justification type.
    """
    zero = Decimal("0")

    if tipo in ("Atraso_Man", "Atraso", "Todos"):
        attendance.delay_morning_min = zero

    if tipo in ("Atraso_Tar", "Atraso", "Todos"):
        attendance.delay_afternoon_min = zero

    if tipo in ("Salida_Anticipada", "Todos"):
        attendance.early_exit_min = zero

    # Recalculate total delay
    morning = attendance.delay_morning_min or zero
    afternoon = attendance.delay_afternoon_min or zero
    attendance.delay_total_min = morning + afternoon
