import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# SQLite connection arguments for concurrency
connect_args = {"check_same_thread": False} if "sqlite" in settings.effective_database_url else {}

engine = create_engine(
    settings.effective_database_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

