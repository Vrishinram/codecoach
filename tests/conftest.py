import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import (
    CurriculumLevel, CurriculumTopic, TopicProgress, UserProfile
)

@pytest.fixture
def db_session():
    """
    Creates an isolated in-memory SQLite database for testing.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    
    # Seed minimal curriculum
    lvl1 = CurriculumLevel(id="csharp-basics", title="C# Basics", order=1)
    lvl2 = CurriculumLevel(id="oop", title="OOP", order=2)
    db.add_all([lvl1, lvl2])
    db.flush()

    t1 = CurriculumTopic(id="variables-and-types", level_id=lvl1.id, title="Variables & Types", order=1, subtopics_json='["primitives", "references"]')
    t2 = CurriculumTopic(id="operators", level_id=lvl1.id, title="Operators", order=2, subtopics_json='["arithmetic", "null-coalescing"]')
    db.add_all([t1, t2])
    db.flush()

    p1 = TopicProgress(topic_id=t1.id, status="Learning", unlocked=True)
    p2 = TopicProgress(topic_id=t2.id, status="New", unlocked=False)
    profile = UserProfile(current_streak=3, longest_streak=5, reminder_times="08:00,20:00")
    db.add_all([p1, p2, profile])
    db.commit()

    yield db
    db.close()

from starlette.testclient import TestClient
from app.main import app
from app.database import get_db

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

