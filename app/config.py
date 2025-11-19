from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    INTAKE_KEY_HEADER_ALIASES: List[str] = []
    INTAKE_HEADER_ROW_INDEX: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",
    )


settings = Settings()