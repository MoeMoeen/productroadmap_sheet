from typing import Dict, List
from pydantic import BaseSettings


class Settings(BaseSettings):
    # App
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # Database (Postgres for v1)
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/prip"

    # OpenAI (provider: OPENAI)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_MAX_TOKENS: int = 2048
    OPENAI_REQUEST_TIMEOUT: int = 60  # seconds

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"
    CENTRAL_BACKLOG_SHEET_ID: str = ""
    CENTRAL_BACKLOG_TAB: str = "Central_Backlog"
    PARAMS_SHEET_ID: str = ""
    PARAMS_TAB: str = "Params"
    MATH_MODELS_SHEET_ID: str = ""
    MATH_MODELS_TAB: str = "MathModels"

    # Intake sheets: name -> sheet_id
    INTAKE_SHEETS: Dict[str, str] = {}

    # Jobs
    CRON_ENABLED: bool = True

    # Intake config (no hardcoded magic numbers)
    INTAKE_CREATE_MAX_RETRIES: int = 3
    INTAKE_ALLOWED_STATUSES: List[str] = ["new", "withdrawn"]
    INTAKE_BATCH_COMMIT_EVERY: int = 100
    INTAKE_KEY_HEADER_NAME: str = "Initiative Key"  # header to locate the key column
    INTAKE_HEADER_ROW_INDEX: int = 1  # header row (1-indexed)

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()