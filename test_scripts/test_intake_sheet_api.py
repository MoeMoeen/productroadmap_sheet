from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import settings


def test_intake():
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds)

    for sheet in settings.INTAKE_SHEETS:
        print(f"\n=== Intake Sheet: {sheet.sheet_key} ===")
        print(f"Spreadsheet ID: {sheet.spreadsheet_id}")

        for tab in sheet.tabs:
            print(f"\n--- Tab: {tab.key} ({tab.tab_name}) ---")
            range_name = f"{tab.tab_name}!A{tab.header_row}:Z"

            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=tab.spreadsheet_id,
                    range=range_name,
                )
                .execute()
            )

            values = result.get("values", [])
            if not values:
                print("  No data found.")
            else:
                print("  First few rows:")
                for row in values[:10]:  # print first 10 rows
                    print("   ", row)


if __name__ == "__main__":
    test_intake()
