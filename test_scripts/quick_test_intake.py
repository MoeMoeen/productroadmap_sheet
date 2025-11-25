# quick_test_intake.py
from app.config import settings

print("Number of intake sheets:", len(settings.INTAKE_SHEETS))
for sheet in settings.INTAKE_SHEETS:
    print("Sheet key:", sheet.sheet_key, "id:", sheet.spreadsheet_id)
    for tab in sheet.tabs:
        print("  Tab:", tab.key, "->", tab.tab_name)

