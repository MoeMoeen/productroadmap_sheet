# productroadmap_sheet_project/app/services/backlog_field_ownership.py
"""Defines ownership of each backlog field (sheet vs DB vs external) to guide reconciliation logic."""
from __future__ import annotations

from app.sheets.models import CENTRAL_EDITABLE_FIELDS, CENTRAL_HEADER_TO_FIELD

OWNER_SHEET = "sheet"
OWNER_DB = "db"
OWNER_EXTERNAL = "external"

# Start from the sheet schema registry, then apply explicit ownership overrides.
FIELD_OWNERSHIP: dict[str, str] = {
    field: (OWNER_SHEET if field in CENTRAL_EDITABLE_FIELDS else OWNER_DB)
    for field in set(CENTRAL_HEADER_TO_FIELD.values())
}

FIELD_OWNERSHIP.update(
    {
        "initiative_key": OWNER_DB,
        "intake_source": OWNER_EXTERNAL,
        "country": OWNER_EXTERNAL,
        "llm_summary": OWNER_DB,
    }
)

SHEET_OWNED_FIELDS = {field for field, owner in FIELD_OWNERSHIP.items() if owner == OWNER_SHEET}
DB_OWNED_FIELDS = {field for field, owner in FIELD_OWNERSHIP.items() if owner == OWNER_DB}
EXTERNAL_OWNED_FIELDS = {field for field, owner in FIELD_OWNERSHIP.items() if owner == OWNER_EXTERNAL}

FIELD_TO_CENTRAL_HEADER = {field: header for header, field in CENTRAL_HEADER_TO_FIELD.items()}


def get_field_owner(field: str) -> str | None:
    return FIELD_OWNERSHIP.get(field)


def is_sheet_owned(field: str) -> bool:
    return FIELD_OWNERSHIP.get(field) == OWNER_SHEET


def is_db_owned(field: str) -> bool:
    return FIELD_OWNERSHIP.get(field) == OWNER_DB


def is_external_owned(field: str) -> bool:
    return FIELD_OWNERSHIP.get(field) == OWNER_EXTERNAL


__all__ = [
    "OWNER_SHEET",
    "OWNER_DB",
    "OWNER_EXTERNAL",
    "FIELD_OWNERSHIP",
    "FIELD_TO_CENTRAL_HEADER",
    "SHEET_OWNED_FIELDS",
    "DB_OWNED_FIELDS",
    "EXTERNAL_OWNED_FIELDS",
    "get_field_owner",
    "is_sheet_owned",
    "is_db_owned",
    "is_external_owned",
]