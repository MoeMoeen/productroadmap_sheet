# productroadmap_sheet_project/app/config.py

from typing import List, Optional
from pathlib import Path
import json

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class IntakeTabConfig(BaseModel):
    key: str
    spreadsheet_id: str
    tab_name: str
    header_row: int = 1
    start_data_row: int = 2
    max_rows: Optional[int] = None
    active: bool = True
    region: Optional[str] = None
    department: Optional[str] = None
    allow_status_override: bool = False


class IntakeSheetConfig(BaseModel):
    sheet_key: str
    spreadsheet_id: str
    region: Optional[str] = None
    description: Optional[str] = None
    tabs: List[IntakeTabConfig] = Field(default_factory=list)

    def active_tabs(self) -> List[IntakeTabConfig]:
        return [t for t in self.tabs if t.active]


class BacklogSheetConfig(BaseModel):
    spreadsheet_id: str
    tab_name: str = "Backlog"
    product_org: Optional[str] = None  # optional label for multi-org


BASE_DIR = Path(__file__).resolve().parent.parent  # project root folder


class Settings(BaseSettings):
    # App
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/prip"

    # OpenAI (provider: OPENAI)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_MAX_TOKENS: int = 2048
    OPENAI_REQUEST_TIMEOUT: int = 60  # seconds

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"

    # Intake: hierarchical config
    INTAKE_SHEETS: List[IntakeSheetConfig] = Field(default_factory=list)

    # NEW: path to JSON file with intake config
    INTAKE_SHEETS_CONFIG_FILE: Optional[str] = None

    # Central backlog (either single default or multiple per org)
    CENTRAL_BACKLOG: Optional[BacklogSheetConfig] = None
    CENTRAL_BACKLOG_SHEETS: List[BacklogSheetConfig] = Field(default_factory=list)

    # Scoring/math/params sheets (global or per org)
    MATH_MODELS_SHEET_ID: Optional[str] = None
    MATH_MODELS_TAB: str = "MathModels"
    PARAMS_SHEET_ID: Optional[str] = None
    PARAMS_TAB: str = "Params"

    # Intake rules (no hardcoded magic numbers)
    INTAKE_CREATE_MAX_RETRIES: int = 3
    INTAKE_ALLOWED_STATUSES: List[str] = ["new", "withdrawn"]
    INTAKE_BATCH_COMMIT_EVERY: int = 100
    INTAKE_KEY_HEADER_NAME: str = "Initiative Key"
    INTAKE_KEY_HEADER_ALIASES: List[str] = ["InitiativeKey", "initiative_key"]
    INTAKE_HEADER_ROW_INDEX: int = 1

    # Scoring
    SCORING_ENABLE_HISTORY: bool = True  # write InitiativeScore rows for audit trail
    SCORING_BATCH_COMMIT_EVERY: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="ignore",
    )

    @model_validator(mode="after")
    def load_intake_sheets_from_file(self) -> "Settings":
        """
        If INTAKE_SHEETS_CONFIG_FILE is set, read that JSON file
        and use it to populate INTAKE_SHEETS.
        """
        if self.INTAKE_SHEETS_CONFIG_FILE:
            cfg_path = Path(self.INTAKE_SHEETS_CONFIG_FILE)
            if not cfg_path.is_absolute():
                cfg_path = BASE_DIR / cfg_path

            if not cfg_path.exists():
                raise FileNotFoundError(
                    f"INTAKE_SHEETS_CONFIG_FILE points to {cfg_path}, but it does not exist."
                )

            with cfg_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)

            if not isinstance(raw, list):
                raise ValueError(
                    "INTAKE_SHEETS config file must contain a JSON list of intake sheet objects."
                )

            self.INTAKE_SHEETS = [
                IntakeSheetConfig.model_validate(item) for item in raw
            ]

        return self


settings = Settings()
