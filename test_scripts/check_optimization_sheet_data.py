"""Check what data exists in Optimization Center sheet tabs"""
from app.config import settings
from app.sheets.client import get_sheets_service, SheetsClient
from app.sheets.optimization_center_readers import (
    ScenarioConfigReader,
    ConstraintsReader,
    TargetsReader,
)

def main():
    print("\n=== Checking Optimization Center Sheet Data ===\n")
    
    if not settings.OPTIMIZATION_CENTER:
        print("ERROR: Optimization Center not configured")
        return
    
    spreadsheet_id = settings.OPTIMIZATION_CENTER.spreadsheet_id
    service = get_sheets_service()
    client = SheetsClient(service)
    
    # Check Scenario_Config tab
    print("📋 Scenario_Config Tab:")
    print("-" * 60)
    scenario_reader = ScenarioConfigReader(client)
    scenarios = scenario_reader.get_rows(spreadsheet_id, "Scenario_Config")
    
    if scenarios:
        print(f"Found {len(scenarios)} scenarios:")
        for row_num, scenario in scenarios:
            print(f"  Row {row_num}: {scenario.scenario_name}")
            print(f"    - capacity_total_tokens: {scenario.capacity_total_tokens}")
            print(f"    - objective_mode: {scenario.objective_mode}")
    else:
        print("  ❌ NO SCENARIOS FOUND")
    
    # Check Constraints tab
    print(f"\n📋 Constraints Tab:")
    print("-" * 60)
    constraints_reader = ConstraintsReader(client)
    constraints = constraints_reader.get_rows(spreadsheet_id, "Constraints")
    
    if constraints:
        print(f"Found {len(constraints)} constraints:")
        for row_num, constraint in constraints[:5]:  # Show first 5
            print(f"  Row {row_num}: scenario={constraint.scenario_name}, constraint_set={constraint.constraint_set_name}")
    else:
        print("  ❌ NO CONSTRAINTS FOUND")
    
    # Check Targets tab
    print(f"\n📋 Targets Tab:")
    print("-" * 60)
    targets_reader = TargetsReader(client)
    targets = targets_reader.get_rows(spreadsheet_id, "Targets")
    
    if targets:
        print(f"Found {len(targets)} targets:")
        for row_num, target in targets[:5]:  # Show first 5
            print(f"  Row {row_num}: scenario={target.scenario_name}, kpi={target.kpi_key}, target={target.target_value}")
    else:
        print("  ❌ NO TARGETS FOUND")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
