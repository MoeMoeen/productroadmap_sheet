# productroadmap_sheet_project/app/db/base.py

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Import all models so that Base.metadata is aware of them
# from app.db.models.initiative import Initiative
# from app.db.models.roadmap_entry import RoadmapEntry  # noqa: F401
# from app.db.models.roadmap import Roadmap  # noqa: F401
# from app.db.models.scoring import InitiativeMathModel, InitiativeScore  # noqa: F401