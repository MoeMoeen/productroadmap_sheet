# productroadmap_sheet_project/test_scripts/init_db.py

"""
Initialize database schema by creating all tables defined by SQLAlchemy models.
"""

from app.db.base import Base
from app.db.session import engine

# Import models here so SQLAlchemy registers them

import app.db.models.initiative
import app.db.models.roadmap_entry
import app.db.models.roadmap
import app.db.models.scoring

def main() -> None:
    print("Creating all tables using SQLAlchemy metadata...")
    Base.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    main()
