from sqlalchemy import create_engine
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
