"""
Backend logic for managing fixed employee schedules.
"""

from sqlalchemy import select
from .database import SessionLocal, EmployeeSchedule

def get_all_employee_schedules() -> list[dict]:
    """
    Fetch all configured employee fixed schedules from the database.
    Returns a list of dicts with keys: employee_id, employee_name, schedule_name.
    """
    session = SessionLocal()
    try:
        stmt = select(EmployeeSchedule).order_by(EmployeeSchedule.employee_name)
        results = session.scalars(stmt).all()
        return [
            {
                "employee_id": item.employee_id,
                "employee_name": item.employee_name,
                "schedule_name": item.schedule_name,
            }
            for item in results
        ]
    finally:
        session.close()

def upsert_employee_schedule(employee_id: str, employee_name: str, schedule_name: str) -> None:
    """
    Insert or update the fixed schedule for a given employee.
    If schedule_name is "Automático", we can either store it or delete/not store.
    Wait, the user approved storing "Automático", which means the database records
    can map employee_id to "Automático", or we can upsert it directly. Let's upsert it.
    """
    session = SessionLocal()
    try:
        stmt = select(EmployeeSchedule).where(EmployeeSchedule.employee_id == employee_id)
        existing = session.scalars(stmt).first()
        if existing:
            existing.schedule_name = schedule_name
            existing.employee_name = employee_name
        else:
            new_sched = EmployeeSchedule(
                employee_id=employee_id,
                employee_name=employee_name,
                schedule_name=schedule_name,
            )
            session.add(new_sched)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
