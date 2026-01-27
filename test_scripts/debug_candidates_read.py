"""Debug script to test reading Candidates tab"""
from app.config import settings
from app.sheets.client import get_sheets_service, SheetsClient
from app.sheets.optimization_center_readers import CandidatesReader
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

def main():
    print("\n=== DEBUG: Reading Candidates Tab ===\n")
    
    if not settings.OPTIMIZATION_CENTER:
        print("ERROR: Optimization Center not configured")
        return
    
    print(f"Spreadsheet ID: {settings.OPTIMIZATION_CENTER.spreadsheet_id}")
    print(f"Candidates Tab: {settings.OPTIMIZATION_CENTER.candidates_tab}\n")
    
    service = get_sheets_service()
    sheets_client = SheetsClient(service)
    
    # Read raw data first
    range_name = f"{settings.OPTIMIZATION_CENTER.candidates_tab}!A1:ZZ"
    result = service.spreadsheets().values().get(
        spreadsheetId=settings.OPTIMIZATION_CENTER.spreadsheet_id,
        range=range_name
    ).execute()
    
    all_rows = result.get("values", [])
    print(f"Total rows in sheet: {len(all_rows)}")
    if all_rows:
        header = all_rows[0]
        print(f"Header columns: {len(header)}")
        print(f"First 5 headers: {header[:5]}")
        print(f"Looking for 'is_selected_for_run' in header...")
        if "is_selected_for_run" in header:
            idx = header.index("is_selected_for_run")
            print(f"  Found at index {idx}")
        else:
            print(f"  NOT FOUND. Available columns: {header}")
        
        # Check ALL rows
        for i, row in enumerate(all_rows[1:], start=2):
            print(f"\nRow {i}: {len(row)} columns")
            if row:
                print(f"  First value: {row[0]}")
                print(f"  All values: {row}")
            else:
                print(f"  EMPTY")
    
    print("\n\nNow trying reader...")
    reader = CandidatesReader(sheets_client)
    
    # Test _read_raw directly
    print("Testing _read_raw...")
    header, data_rows = reader._read_raw(
        spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
        tab_name=settings.OPTIMIZATION_CENTER.candidates_tab
    )
    print(f"Header from _read_raw: {len(header)} columns")
    print(f"Data rows from _read_raw: {len(data_rows)} rows")
    if data_rows:
        print(f"First data row: {data_rows[0][:5] if data_rows[0] else 'EMPTY'}")
    
    print("\nReading candidates with full logging...")
    import sys
    from io import StringIO
    
    # Capture warnings
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    candidates_with_rows = reader.get_rows(
        spreadsheet_id=settings.OPTIMIZATION_CENTER.spreadsheet_id,
        tab_name=settings.OPTIMIZATION_CENTER.candidates_tab,
    )
    
    # Restore stdout
    captured = sys.stdout.getvalue()
    sys.stdout = old_stdout
    
    if captured:
        print(f"Captured output:\n{captured}")
    
    print(f"\nTotal candidates read: {len(candidates_with_rows)}\n")
    
    for row_num, candidate in candidates_with_rows:
        print(f"Row {row_num}:")
        print(f"  initiative_key: {candidate.initiative_key}")
        print(f"  is_selected_for_run: {candidate.is_selected_for_run}")
        print(f"  engineering_tokens: {candidate.engineering_tokens}")
        print()
    
    # Filter for selected
    selected = [(row, c) for row, c in candidates_with_rows 
                if getattr(c, "is_selected_for_run", False)]
    
    print(f"\nSelected candidates (is_selected_for_run=TRUE): {len(selected)}")
    for row_num, candidate in selected:
        print(f"  Row {row_num}: {candidate.initiative_key}")

if __name__ == "__main__":
    main()
