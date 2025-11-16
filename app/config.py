from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Intake sheets: name -> sheet_id (optionally encode tab in your reader)
    # Example env usage: INTAKE_SHEETS__UK_SALES=1Abc... INTAKE_SHEETS__FR_MARKETING=1Xyz...
    INTAKE_SHEETS: Dict[str, str] = {}

    # Jobs
    CRON_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",  # allows INTAKE_SHEETS__KEY=value
    )


settings = Settings()