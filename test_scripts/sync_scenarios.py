"""Sync scenarios from Optimization Center sheet to database"""
from app.config import settings
from app.db.session import SessionLocal
from app.db.models.optimization import OptimizationScenario
from app.sheets.client import get_sheets_service, SheetsClient
from app.services.optimization.optimization_sync_service import sync_scenarios_from_sheet

def main():
    print("\n=== Syncing Scenarios from Sheet to DB ===\n")
    
    if not settings.OPTIMIZATION_CENTER:
        print("ERROR: Optimization Center not configured")
        return
    
    spreadsheet_id = settings.OPTIMIZATION_CENTER.spreadsheet_id
    scenario_config_tab = settings.OPTIMIZATION_CENTER.scenario_config_tab or "Scenario_Config"
    
    service = get_sheets_service()
    client = SheetsClient(service)
    
    # Use the proper service function
    synced_scenarios, errors = sync_scenarios_from_sheet(
        sheets_client=client,
        spreadsheet_id=spreadsheet_id,
        scenario_config_tab=scenario_config_tab,
    )
    
    if errors:
        print("⚠️  Errors encountered:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    print(f"✅ Synced {len(synced_scenarios)} scenarios to database\n")
    
    # Verify
    print("📋 Scenarios now in database:")
    db = SessionLocal()
    try:
        all_scenarios = db.query(OptimizationScenario).all()
        for s in all_scenarios:
            print(f"  - {s.name} (id={s.id}, capacity={s.capacity_total_tokens}, mode={s.objective_mode})")
    finally:
        db.close()

if __name__ == "__main__":
    main()
