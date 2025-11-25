from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import settings


def main() -> None:
    # 1) Load credentials from your service account JSON
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )

    # 2) Build the Sheets API client
    service = build("sheets", "v4", credentials=creds)

    # 3) Use CENTRAL_BACKLOG from your settings
    if settings.CENTRAL_BACKLOG is None:
        raise RuntimeError("CENTRAL_BACKLOG is not configured in .env")

    spreadsheet_id = settings.CENTRAL_BACKLOG.spreadsheet_id
    tab_name = settings.CENTRAL_BACKLOG.tab_name or "Backlog"

    # We’ll read first 10 rows & 5 columns from that tab
    range_name = f"{tab_name}!A1:E10"

    print(f"Reading range {range_name} from spreadsheet {spreadsheet_id}...")

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )

    values = result.get("values", [])

    if not values:
        print("No data found in that range.")
    else:
        print("Data:")
        for row in values:
            print(row)


if __name__ == "__main__":
    main()
