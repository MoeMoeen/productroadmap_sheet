from sqlalchemy.orm import Session
from app.sheets.intake_writer import GoogleSheetsIntakeWriter
from app.services.intake_service import IntakeService

def run_sync(db: Session, rows, sheet_id: str, tab: str, start_row: int):
    key_writer = GoogleSheetsIntakeWriter()
    service = IntakeService(db, key_writer=key_writer)
    service.upsert_many(rows, sheet_id, tab, start_row_number=start_row)