-- ============================================================
-- SEFIL Attendance System – PostgreSQL Schema Initialization
-- This script runs automatically on first container start via
-- /docker-entrypoint-initdb.d/
-- ============================================================

-- attendance_daily: stores daily attendance records from Excel sync
CREATE TABLE IF NOT EXISTS attendance_daily (
    id                  SERIAL PRIMARY KEY,
    employee_id         VARCHAR(20)   NOT NULL,
    employee_name       VARCHAR(100)  NOT NULL,
    date                DATE          NOT NULL,
    schedule_name       VARCHAR(50),
    shift_type          VARCHAR(20),
    shift_detail        VARCHAR(20),
    shift_str           VARCHAR(100),
    entry_morning       TIME,
    exit_morning        TIME,
    entry_afternoon     TIME,
    exit_afternoon      TIME,
    hours_morning       DECIMAL(5,2)  DEFAULT 0,
    hours_afternoon     DECIMAL(5,2)  DEFAULT 0,
    hours_total         DECIMAL(5,2)  DEFAULT 0,
    delay_morning_min   DECIMAL(5,2)  DEFAULT 0,
    delay_afternoon_min DECIMAL(5,2)  DEFAULT 0,
    delay_total_min     DECIMAL(5,2)  DEFAULT 0,
    early_exit_min      DECIMAL(5,2)  DEFAULT 0,
    overtime_hours      DECIMAL(5,2)  DEFAULT 0,
    event               VARCHAR(50),
    annotations         TEXT,
    month_period        VARCHAR(7),
    created_at          TIMESTAMP     DEFAULT NOW(),
    UNIQUE(employee_id, date)
);

-- justifications: replaces justificaciones.xlsx
CREATE TABLE IF NOT EXISTS justifications (
    id              SERIAL PRIMARY KEY,
    employee_id     VARCHAR(20)  NOT NULL,
    employee_name   VARCHAR(100),
    date            DATE         NOT NULL,
    type            VARCHAR(30)  NOT NULL CHECK (type IN (
                        'Atraso_Man',
                        'Atraso_Tar',
                        'Atraso',
                        'Salida_Anticipada',
                        'Todos'
                    )),
    reason          TEXT         NOT NULL,
    applied         BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT NOW(),
    UNIQUE(employee_id, date, type)
);

-- sync_log: tracks sync operations
CREATE TABLE IF NOT EXISTS sync_log (
    id                SERIAL PRIMARY KEY,
    synced_at         TIMESTAMP    DEFAULT NOW(),
    records_added     INT          DEFAULT 0,
    records_skipped   INT          DEFAULT 0,
    date_range_start  DATE,
    date_range_end    DATE,
    source_file       VARCHAR(255),
    status            VARCHAR(20)  DEFAULT 'success'
);

-- ── Indexes for dashboard performance ───────────────────
CREATE INDEX IF NOT EXISTS idx_attendance_date      ON attendance_daily(date);
CREATE INDEX IF NOT EXISTS idx_attendance_employee   ON attendance_daily(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_month      ON attendance_daily(month_period);
CREATE INDEX IF NOT EXISTS idx_justifications_emp_date ON justifications(employee_id, date);
