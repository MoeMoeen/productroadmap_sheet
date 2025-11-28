# productroadmap_sheet_project/test_scripts/run_intake_sync_once.py
"""Run intake sync once for testing purposes."""
from app.db.session import SessionLocal
from app.jobs.sync_intake_job import run_sync_all_intake_sheets
from app.config import settings


def main():
    print("ENV:", settings.ENV)
    print("Intake sheets:", [s.sheet_key for s in settings.INTAKE_SHEETS])

    db = SessionLocal()
    try:
        run_sync_all_intake_sheets(
            db=db,
            allow_status_override_global=False
        )
    finally:
        db.close()

if __name__ == "__main__":
    main()
