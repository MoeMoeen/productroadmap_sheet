#!/usr/bin/env python3
"""
Sync constraints and targets from Optimization Center sheet to DB using correct config and modules.
"""
from app.config import Settings
from app.db.session import SessionLocal
from app.sheets.client import get_sheets_service, SheetsClient
from app.services.optimization.optimization_sync_service import sync_constraint_sets_from_sheets

if __name__ == "__main__":
    # Load config for Optimization Center
    settings = Settings().load_optimization_center_from_file()
    opt = settings.OPTIMIZATION_CENTER
    service = get_sheets_service()
    sheets_client = SheetsClient(service)
    db = SessionLocal()

    constraint_sets, messages = sync_constraint_sets_from_sheets(
        sheets_client=sheets_client,
        spreadsheet_id=opt.spreadsheet_id,
        constraints_tab=opt.constraints_tab,
        targets_tab=opt.targets_tab,
        session=db,
    )

    print(f"✓ Synced {len(constraint_sets)} constraint sets")
    for msg in messages:
        print(f"  {msg.level}: {msg.message}")

    db.close()
