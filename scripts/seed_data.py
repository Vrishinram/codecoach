"""
Database Seed Script: Populates curriculum levels, topics, and curated learning links.
Run:
    python scripts/seed_data.py
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app.database import engine, Base, SessionLocal
from app.services.curriculum_service import seed_curriculum_if_needed
from app.services.link_validator import seed_links_if_needed

def main():
    print("Creating tables if not present...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Seeding curriculum topics...")
        seed_curriculum_if_needed(db)
        print("Seeding curated links...")
        seed_links_if_needed(db)
        print("Done! Database is seeded and ready.")
    finally:
        db.close()

if __name__ == "__main__":
    main()

