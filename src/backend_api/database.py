from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base
import os

# SQLite remains convenient locally; production-sized registries should set a
# server database URL such as PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./road_user_platform.db")

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    # This flag is SQLite-only and is needed when FastAPI uses worker threads.
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns()


def _ensure_runtime_columns():
    inspector = inspect(engine)
    if "violations" not in inspector.get_table_names():
        return

    violation_columns = {column["name"] for column in inspector.get_columns("violations")}
    if "evidence_image_path" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN evidence_image_path VARCHAR"))
    if "evidence_media_path" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN evidence_media_path VARCHAR"))
    if "evidence_media_type" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN evidence_media_type VARCHAR"))
    if "review_status" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN review_status VARCHAR"))
    if "review_notes" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN review_notes VARCHAR"))
    if "reviewed_at" not in violation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE violations ADD COLUMN reviewed_at DATETIME"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
