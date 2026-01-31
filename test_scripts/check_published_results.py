"""Check if optimization results were published to sheets."""
from app.sheets.google_client import get_sheets_service, SheetsClient
from app.config import settings

service = get_sheets_service()
client = SheetsClient(service)

# Check Runs tab
print("=" * 60)
print("Checking Published Optimization Results")
print("=" * 60)

runs_data = client.get_values(
    settings.OPTIMIZATION_CENTER.spreadsheet_id,
    f"{settings.OPTIMIZATION_CENTER.runs_tab}!A1:S20"
)
print(f"\n📊 Runs Tab: {len(runs_data)} rows")
if len(runs_data) > 3:
    print(f"  Header: {runs_data[0][:6]}")
    print(f"  Data rows: {len(runs_data) - 3}")
    for i, row in enumerate(runs_data[3:], start=4):
        if row:  # Skip empty rows
            run_id = row[0] if len(row) > 0 else ""
            scenario = row[1] if len(row) > 1 else ""
            status = row[3] if len(run) > 3 else ""
            print(f"  Row {i}: run_id={run_id}, scenario={scenario}, status={status}")
else:
    print("  ⚠️  No data rows found (only header + metadata)")

# Check Results tab
results_data = client.get_values(
    settings.OPTIMIZATION_CENTER.spreadsheet_id,
    f"{settings.OPTIMIZATION_CENTER.results_tab}!A1:S20"
)
print(f"\n📊 Results Tab: {len(results_data)} rows")
if len(results_data) > 3:
    print(f"  Header: {results_data[0][:6]}")
    print(f"  Data rows: {len(results_data) - 3}")
    for i, row in enumerate(results_data[3:7], start=4):  # Show first 4 data rows
        if row:
            run_id = row[0] if len(row) > 0 else ""
            init_key = row[1] if len(row) > 1 else ""
            selected = row[2] if len(row) > 2 else ""
            print(f"  Row {i}: run_id={run_id}, initiative={init_key}, selected={selected}")
else:
    print("  ⚠️  No data rows found (only header + metadata)")

# Check Gaps tab
gaps_data = client.get_values(
    settings.OPTIMIZATION_CENTER.spreadsheet_id,
    f"{settings.OPTIMIZATION_CENTER.gaps_tab}!A1:M20"
)
print(f"\n📊 Gaps Tab: {len(gaps_data)} rows")
if len(gaps_data) > 3:
    print(f"  Header: {gaps_data[0][:6]}")
    print(f"  Data rows: {len(gaps_data) - 3}")
    for i, row in enumerate(gaps_data[3:7], start=4):  # Show first 4 data rows
        if row:
            run_id = row[0] if len(row) > 0 else ""
            kpi_key = row[1] if len(row) > 1 else ""
            target = row[2] if len(row) > 2 else ""
            achieved = row[3] if len(row) > 3 else ""
            gap = row[4] if len(row) > 4 else ""
            print(f"  Row {i}: run_id={run_id}, kpi={kpi_key}, target={target}, achieved={achieved}, gap={gap}")
else:
    print("  ⚠️  No data rows found (only header + metadata)")

print("\n" + "=" * 60)
print("✓ Check complete")
print("=" * 60)
