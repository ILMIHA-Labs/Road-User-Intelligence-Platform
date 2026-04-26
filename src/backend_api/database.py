from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base
import os

# Use SQLite for MVP, easy to swap to postgresql://user:pass@host/db later
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./road_user_platform.db")

# connect_args={"check_same_thread": False} is needed only for SQLite
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} 
)
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
