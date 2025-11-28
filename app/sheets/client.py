# productroadmap_sheet_project/app/sheets/client.py

from __future__ import annotations

from typing import Any, List

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from app.config import settings


def get_sheets_service():
    """Create and return a Google Sheets API service client."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    # cache_discovery=False avoids file system writes in some environments
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


class SheetsClient:
    """Thin wrapper around Google Sheets API values endpoints.

    - get_values returns evaluated values (not formulas) by default.
    - update_values writes a 2D block with USER_ENTERED semantics by default.
    """

    def __init__(self, service) -> None:
        self.service = service

    def get_values(
        self,
        spreadsheet_id: str,
        range_: str,
        value_render_option: str = "UNFORMATTED_VALUE",
    ) -> List[List[Any]]:
        """Get values from a given spreadsheet and range."""
        resp = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueRenderOption=value_render_option,
            )
            .execute()
        )
        return resp.get("values", [])

    def update_values(
        self,
        spreadsheet_id: str,
        range_: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> None:
        """Update values in a given spreadsheet and range."""
        body = {"values": values}
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueInputOption=value_input_option,
                body=body,
            )
            .execute()
        )

    def get_sheet_grid_size(self, spreadsheet_id: str, tab_name: str) -> tuple[int, int]:
        """Return (rowCount, columnCount) for a given tab by title.

        Uses spreadsheets.get with minimal fields for performance.
        """
        resp = (
            self.service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties(title,gridProperties)")
            .execute()
        )
        sheets = resp.get("sheets", [])
        for sh in sheets:
            props = sh.get("properties", {})
            if props.get("title") == tab_name:
                grid = props.get("gridProperties", {})
                rows = int(grid.get("rowCount", 1000))
                cols = int(grid.get("columnCount", 26))
                return rows, cols
        # Fallback defaults if tab not found
        return 1000, 26

    def get_sheet_properties(self, spreadsheet_id: str, tab_name: str) -> dict:
        """Return sheet properties and protected ranges for a tab by title.

        Returns a dict with keys: sheetId, title, gridProperties, protectedRanges (optional).
        """
        resp = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(title,sheetId,gridProperties),protectedRanges)",
            )
            .execute()
        )
        for sheet in resp.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == tab_name:
                out = {
                    "sheetId": props.get("sheetId"),
                    "title": props.get("title"),
                    "gridProperties": props.get("gridProperties", {}),
                }
                # protectedRanges are on the sheet object itself
                if sheet.get("protectedRanges") is not None:
                    out["protectedRanges"] = sheet.get("protectedRanges")
                return out
        return {}

    def batch_update(self, spreadsheet_id: str, requests: list[dict]) -> None:
        """Send a batchUpdate with the provided list of requests."""
        if not requests:
            return
        body = {"requests": requests}
        (
            self.service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )
    