from __future__ import annotations

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from app.config import settings


def get_sheets_service():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)