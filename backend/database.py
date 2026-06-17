"""
Database connection and ORM models for the SEFIL attendance system.
Uses SQLAlchemy 2.0+ style with PostgreSQL.
"""

import os
from datetime import date, datetime, time

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Environment & connection
# ---------------------------------------------------------------------------
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sefil:SefilDB2026!@localhost:5432/sefil_asistencias",
)

# Si se ejecuta fuera de Docker (en el host de Windows) y DATABASE_URL apunta al contenedor "postgres",
# redirigir automáticamente al puerto expuesto en localhost (5434 en docker-compose.yml).
if not os.path.exists("/.dockerenv") and "@postgres:5432" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("@postgres:5432", "@localhost:5434")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------
class AttendanceDaily(Base):
    """One row per employee per day with full attendance detail."""

    __tablename__ = "attendance_daily"
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_employee_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(20), nullable=False)
    employee_name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)

    # Schedule / shift
    schedule_name = Column(String(50))     # e.g. 'Horario A', 'Horario B', 'Medio Tiempo'
    shift_type = Column(String(20))        # 'Completa', 'Media', 'Especial'
    shift_detail = Column(String(20))      # 'completo', 'mañana', 'tarde', 'especial'
    shift_str = Column(String(100))        # e.g. '08:00-13:00 / 14:00-17:00'

    # Clock-in / clock-out times
    entry_morning = Column(Time, nullable=True)
    exit_morning = Column(Time, nullable=True)
    entry_afternoon = Column(Time, nullable=True)
    exit_afternoon = Column(Time, nullable=True)

    # Worked hours
    hours_morning = Column(Numeric(5, 2), default=0)
    hours_afternoon = Column(Numeric(5, 2), default=0)
    hours_total = Column(Numeric(5, 2), default=0)

    # Delays
    delay_morning_min = Column(Numeric(5, 2), default=0)
    delay_afternoon_min = Column(Numeric(5, 2), default=0)
    delay_total_min = Column(Numeric(5, 2), default=0)

    # Early exit & overtime
    early_exit_min = Column(Numeric(5, 2), default=0)
    overtime_hours = Column(Numeric(5, 2), default=0)

    # Metadata
    event = Column(String(50))
    annotations = Column(Text)
    month_period = Column(String(7))       # e.g. '2026-01'

    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<AttendanceDaily(id={self.id}, employee={self.employee_id}, "
            f"date={self.date})>"
        )


class Justification(Base):
    """Justifications that zero-out delays / early-exits for an employee-day."""

    __tablename__ = "justifications"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "date", "type", name="uq_justification_employee_date_type"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(20), nullable=False)
    employee_name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    type = Column(String(30), nullable=False)
    reason = Column(Text)
    applied = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<Justification(id={self.id}, employee={self.employee_id}, "
            f"date={self.date}, type={self.type})>"
        )


class ManualSchedule(Base):
    """Manual overrides for schedules or rest days assigned from the interactive calendar."""

    __tablename__ = "manual_schedules"
    __table_args__ = (
        UniqueConstraint("employee_name", "date", name="uq_manual_sched_emp_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False)
    assigned_status = Column(String(50), nullable=False)  # e.g., 'Descanso', 'Horario A'
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ManualSchedule(id={self.id}, employee={self.employee_name}, "
            f"date={self.date}, status={self.assigned_status})>"
        )


class SyncLog(Base):
    """Audit log for each Excel → DB synchronisation run."""

    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    synced_at = Column(DateTime, server_default=func.now())
    records_added = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    date_range_start = Column(Date)
    date_range_end = Column(Date)
    source_file = Column(String(255))
    status = Column(String(30))

    def __repr__(self) -> str:
        return (
            f"<SyncLog(id={self.id}, added={self.records_added}, "
            f"skipped={self.records_skipped}, status={self.status})>"
        )


class EmployeeSchedule(Base):
    """Fixed schedule assignments per employee."""

    __tablename__ = "employee_schedules"

    employee_id = Column(String(20), primary_key=True)
    employee_name = Column(String(100), nullable=False)
    schedule_name = Column(String(50), nullable=False)  # 'Automático', 'Horario A', 'Horario B', etc.
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<EmployeeSchedule(id={self.employee_id}, name={self.employee_name}, "
            f"schedule={self.schedule_name})>"
        )


class User(Base):
    """System users with roles for Dashboard authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="rrhh")  # 'admin' or 'rrhh'
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<User(username={self.username}, role={self.role})>"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_session():
    """Return a new SQLAlchemy session."""
    return SessionLocal()


def get_engine():
    """Return the shared SQLAlchemy engine."""
    return engine


def init_db():
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


# Auto-initialize database tables on module import
init_db()
