import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import ConfigError, current_env, database_url_problem


def _resolve_database_url() -> str:
    """
    Production: DATABASE_URL is required and must be PostgreSQL — no SQLite fallback, never /tmp.
    Development: DATABASE_URL if given (SQLite or PostgreSQL), else a SQLite file in backend/data.
    Tests: DATABASE_URL if given, else an in-memory SQLite database (nothing written to disk).
    """
    env = current_env()
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if env == "production":
        problem = database_url_problem(url)
        if problem:
            raise ConfigError(problem)
        return url
    if url:
        return url
    if env == "test":
        return "sqlite://"
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'interview_ai.db').as_posix()}"


DATABASE_URL = _resolve_database_url()

if not DATABASE_URL.startswith("sqlite"):
    # ── PostgreSQL with high-concurrency connection pooling ──
    engine = create_engine(
        DATABASE_URL,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "30")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "50")),
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        poolclass=QueuePool,
        connect_args={"connect_timeout": 10},
        echo=False,
    )
elif DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
    # ── In-memory SQLite (tests): one shared connection so every session sees the same data ──
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
else:
    # ── SQLite file (development) with high-concurrency WAL + memory-mapped I/O ──
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15},
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
    )

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA cache_size=-64000")       # 64MB page cache in RAM
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")     # 256MB memory-mapped I/O
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def verify_database_connection() -> None:
    """
    One round trip to the database. Production calls it at startup, so a wrong host, password or
    database name stops the process with a clear message instead of serving 500s. The driver's own
    message is left out: it can echo the host and user of the connection string.
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        raise ConfigError(
            f"Could not connect to the database in DATABASE_URL ({type(e).__name__}). "
            "Check the host, port, user, password and database name, and that this server may reach it."
        ) from None


def _migration_engine():
    """DDL (ALTER TABLE) needs a direct Postgres connection — not Supabase transaction pooler (port 6543)."""
    direct_url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DIRECT_URL")
    if direct_url:
        return create_engine(direct_url, pool_pre_ping=True)
    return engine


def _column_exists(table: str, column: str, eng=None) -> bool:
    from sqlalchemy import inspect
    eng = eng or engine
    insp = inspect(eng)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _exec_ddl(ddl: str) -> None:
    from sqlalchemy import text
    mig_eng = _migration_engine()
    if mig_eng.dialect.name == "postgresql":
        with mig_eng.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            # Never wait forever for a table lock held by another (old) instance.
            conn.execute(text("SET lock_timeout = '5s'"))
            conn.execute(text("SET statement_timeout = '60s'"))
            conn.execute(text(ddl))
    else:
        with mig_eng.begin() as conn:
            conn.execute(text(ddl))


def _add_column(table: str, column: str, ddl: str) -> None:
    if _column_exists(table, column):
        return
    _exec_ddl(ddl)
    print(f"[DB Migration] Added {table}.{column}")


def run_migrations():
    """Lightweight schema patches + high-scale index creation for SQLite / PostgreSQL."""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(engine)
        table_names = set(insp.get_table_names())
        if "users" not in table_names:
            print("[DB Migration] users table not found — skipping patches")
            return

        is_pg = engine.dialect.name == "postgresql"
        bool_false = "FALSE" if is_pg else "0"
        bool_true = "TRUE" if is_pg else "1"
        len_fn = "char_length" if is_pg else "length"

        if is_pg:
            _add_column("users", "voice_locked", "ALTER TABLE users ADD COLUMN IF NOT EXISTS voice_locked BOOLEAN DEFAULT FALSE")
            _add_column("users", "voice_reenroll_allowed", "ALTER TABLE users ADD COLUMN IF NOT EXISTS voice_reenroll_allowed BOOLEAN DEFAULT FALSE")
            _add_column("users", "face_embedding", "ALTER TABLE users ADD COLUMN IF NOT EXISTS face_embedding TEXT")
            _add_column("users", "face_locked", "ALTER TABLE users ADD COLUMN IF NOT EXISTS face_locked BOOLEAN DEFAULT FALSE")
            _add_column("users", "plan_tier", "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_tier VARCHAR DEFAULT 'free'")
            _add_column("users", "plan_updated_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_updated_at VARCHAR")
            _add_column("users", "exams_created_count", "ALTER TABLE users ADD COLUMN IF NOT EXISTS exams_created_count INTEGER DEFAULT 0")
        else:
            _add_column("users", "voice_locked", f"ALTER TABLE users ADD COLUMN voice_locked BOOLEAN DEFAULT {bool_false}")
            _add_column("users", "voice_reenroll_allowed", f"ALTER TABLE users ADD COLUMN voice_reenroll_allowed BOOLEAN DEFAULT {bool_false}")
            _add_column("users", "face_embedding", "ALTER TABLE users ADD COLUMN face_embedding TEXT")
            _add_column("users", "face_locked", f"ALTER TABLE users ADD COLUMN face_locked BOOLEAN DEFAULT {bool_false}")
            _add_column("users", "plan_tier", "ALTER TABLE users ADD COLUMN plan_tier VARCHAR DEFAULT 'free'")
            _add_column("users", "plan_updated_at", "ALTER TABLE users ADD COLUMN plan_updated_at VARCHAR")
            _add_column("users", "exams_created_count", "ALTER TABLE users ADD COLUMN exams_created_count INTEGER DEFAULT 0")

        with engine.begin() as conn:
            conn.execute(text(
                f"UPDATE users SET voice_locked = {bool_true} "
                f"WHERE voice_embedding IS NOT NULL AND {len_fn}(voice_embedding) > 10 "
                f"AND (voice_locked IS NULL OR voice_locked = {bool_false})"
            ))
            conn.execute(text(
                f"UPDATE users SET face_locked = {bool_true} "
                f"WHERE face_embedding IS NOT NULL AND {len_fn}(face_embedding) > 10 "
                f"AND (face_locked IS NULL OR face_locked = {bool_false})"
            ))
            conn.execute(text(
                "UPDATE users SET plan_tier = 'free' WHERE plan_tier IS NULL OR plan_tier = ''"
            ))

        _exec_ddl("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")
        _exec_ddl("CREATE INDEX IF NOT EXISTS ix_users_plan_tier ON users (plan_tier)")

        if "questions" in table_names:
            # Exams that existed before attempt limits get 1 attempt, the product default.
            ine = "IF NOT EXISTS " if is_pg else ""
            _add_column("questions", "max_attempts",
                        f"ALTER TABLE questions ADD COLUMN {ine}max_attempts INTEGER NOT NULL DEFAULT 1")
            # Existing exams keep publishing by hand (their per-answer grade_visible is untouched).
            _add_column("questions", "results_policy",
                        f"ALTER TABLE questions ADD COLUMN {ine}results_policy VARCHAR(16) NOT NULL DEFAULT 'manual'")
            _add_column("questions", "results_published_at",
                        f"ALTER TABLE questions ADD COLUMN {ine}results_published_at TIMESTAMP")
            _add_column("questions", "results_published_by",
                        f"ALTER TABLE questions ADD COLUMN {ine}results_published_by INTEGER")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_questions_creator_id ON questions (creator_id)")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_questions_exam_token ON questions (exam_token)")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_questions_group_token ON questions (group_token, order_index)")

        if "exam_submissions" in table_names:
            if is_pg:
                _add_column("exam_submissions", "face_score", "ALTER TABLE exam_submissions ADD COLUMN IF NOT EXISTS face_score DOUBLE PRECISION")
                _add_column("exam_submissions", "submission_key", "ALTER TABLE exam_submissions ADD COLUMN IF NOT EXISTS submission_key VARCHAR")
                _add_column("exam_submissions", "grading_status", "ALTER TABLE exam_submissions ADD COLUMN IF NOT EXISTS grading_status VARCHAR(16) NOT NULL DEFAULT 'completed'")
            else:
                _add_column("exam_submissions", "face_score", "ALTER TABLE exam_submissions ADD COLUMN face_score FLOAT")
                _add_column("exam_submissions", "submission_key", "ALTER TABLE exam_submissions ADD COLUMN submission_key VARCHAR")
                _add_column("exam_submissions", "grading_status", "ALTER TABLE exam_submissions ADD COLUMN grading_status VARCHAR(16) NOT NULL DEFAULT 'completed'")
            # H1 evidence columns and H2 sitting/attempt: NULL on existing rows (left exactly as graded;
            # NULLs never collide in the unique indexes below).
            for col, col_type in (("face_verification", "VARCHAR(16)"), ("face_checks", "INTEGER"),
                                  ("integrity_status", "VARCHAR(24)"), ("client_alerts", "TEXT"),
                                  ("exam_sitting_id", "INTEGER"), ("attempt_no", "INTEGER")):
                ine = "IF NOT EXISTS " if is_pg else ""
                _add_column("exam_submissions", col, f"ALTER TABLE exam_submissions ADD COLUMN {ine}{col} {col_type}")
            _exec_ddl("CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_submissions_attempt "
                      "ON exam_submissions (student_id, question_id, attempt_no)")
            _exec_ddl("CREATE UNIQUE INDEX IF NOT EXISTS ux_exam_submissions_sitting_question "
                      "ON exam_submissions (exam_sitting_id, question_id)")

            _exec_ddl(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_exam_submissions_submission_key "
                "ON exam_submissions (submission_key)"
            )
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_exam_submissions_question_id ON exam_submissions (question_id)")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_exam_submissions_q_submitted ON exam_submissions (question_id, submitted_at)")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_exam_submissions_student_id ON exam_submissions (student_id, grade_visible)")

        if "exam_assignments" in table_names:
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_exam_assignments_student_status ON exam_assignments (student_id, status)")
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_exam_assignments_question_id ON exam_assignments (question_id)")

        if "payments" in table_names:
            _exec_ddl("CREATE INDEX IF NOT EXISTS ix_payments_user_status ON payments (user_id, status)")
            # H8: gateway order kept after payment (refund mapping), one open payment per account,
            # pending -> review after 24h, refunds. NULL on existing rows: legacy pending payments
            # are still found by the checkout's status query, only the index does not cover them.
            ine = "IF NOT EXISTS " if is_pg else ""
            for col, col_type in (("provider_order_ref", "VARCHAR(128)"), ("open_slot", "INTEGER"),
                                  ("checkout_url", "TEXT"), ("checkout_expires_at", "TIMESTAMP"),
                                  ("review_at", "TIMESTAMP"), ("refunded_at", "TIMESTAMP"),
                                  ("refunded_amount_minor", "INTEGER")):
                _add_column("payments", col, f"ALTER TABLE payments ADD COLUMN {ine}{col} {col_type}")
            for ddl in ("CREATE INDEX IF NOT EXISTS ix_payments_provider_order_ref ON payments (provider_order_ref)",
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_one_open ON payments (user_id, open_slot)"):
                try:
                    _exec_ddl(ddl)
                except Exception as e:  # never block the remaining patches on one index
                    print(f"[DB Migration] WARNING: {ddl.split(' ON ')[0]} failed: {e}")

        _run_billing_migrations(is_pg, "questions" in table_names)

        print("[DB Migration] All patches and scalability indexes applied successfully")
        return {"ok": True, "face_embedding": _column_exists("users", "face_embedding")}
    except Exception as e:
        print(f"[DB Migration] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


_migrations_applied = False


def _run_billing_migrations(is_pg: bool, has_questions: bool) -> None:
    """Subscription-cycle columns on users + keep the lifetime exam counter consistent."""
    from sqlalchemy import text

    billing_columns = [
        ("plan_period", "VARCHAR"),
        ("plan_started_at", "TIMESTAMP"),
        ("plan_expires_at", "TIMESTAMP"),
        ("cycle_started_at", "TIMESTAMP"),
        ("cycle_exams_used", "INTEGER DEFAULT 0"),
        ("bonus_exams", "INTEGER DEFAULT 0"),
        ("custom_max_exams", "INTEGER"),
        ("custom_max_students", "INTEGER"),
        ("owner_id", "INTEGER"),
    ]
    for col, col_type in billing_columns:
        if is_pg:
            _add_column("users", col, f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}")
        else:
            _add_column("users", col, f"ALTER TABLE users ADD COLUMN {col} {col_type}")

    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET cycle_exams_used = 0 WHERE cycle_exams_used IS NULL"))
        conn.execute(text("UPDATE users SET bonus_exams = 0 WHERE bonus_exams IS NULL"))
        conn.execute(text("UPDATE users SET exams_created_count = 0 WHERE exams_created_count IS NULL"))
        if has_questions:
            # Lifetime counter must never be below the exams that still exist (legacy rows).
            conn.execute(text(
                "UPDATE users SET exams_created_count = ("
                "  SELECT COUNT(DISTINCT COALESCE(q.group_token, q.exam_token)) "
                "  FROM questions q WHERE q.creator_id = users.id"
                ") WHERE exams_created_count < ("
                "  SELECT COUNT(DISTINCT COALESCE(q.group_token, q.exam_token)) "
                "  FROM questions q WHERE q.creator_id = users.id"
                ")"
            ))
    _exec_ddl("CREATE INDEX IF NOT EXISTS ix_users_owner_id ON users (owner_id)")
    _run_email_ownership_migrations(is_pg)


def _run_email_ownership_migrations(is_pg: bool) -> None:
    """
    E-mail ownership columns. Existing accounts get email_verified = FALSE (nobody proved the
    address) and requires_email_verification = FALSE (they predate the check, so they are not
    locked out). New sign-ups are inserted with requires_email_verification = TRUE by the model.
    """
    false = "FALSE" if is_pg else "0"
    columns = [
        ("email_verified", f"BOOLEAN NOT NULL DEFAULT {false}"),
        ("email_verified_at", "TIMESTAMP"),
        ("requires_email_verification", f"BOOLEAN NOT NULL DEFAULT {false}"),
        ("google_sub", "VARCHAR(255)"),
        ("token_version", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col, col_type in columns:
        if is_pg:
            _add_column("users", col, f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}")
        else:
            _add_column("users", col, f"ALTER TABLE users ADD COLUMN {col} {col_type}")
    _exec_ddl("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)")


_migrations_applied = False


def ensure_migrations() -> dict:
    """Run migrations once per process."""
    global _migrations_applied
    if _migrations_applied:
        return {"ok": True, "cached": True}
    result = run_migrations()
    if result and result.get("ok"):
        _migrations_applied = True
    return result or {"ok": False}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
