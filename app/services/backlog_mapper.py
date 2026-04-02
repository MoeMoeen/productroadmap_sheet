#productroadmap_sheet_project/app/services/backlog_mapper.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.sheets.backlog_reader import BacklogRow  # type: ignore
from app.sheets.models import CENTRAL_EDITABLE_FIELDS, CENTRAL_HEADER_TO_FIELD
from app.utils.header_utils import get_value_by_header_alias

def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"true", "yes", "y", "1", "✅", "✔", "ok"}


def _split_keys(value: Any) -> List[str]:
    if not value:
        return []
    s = str(value)
    parts = [part.strip() for part in s.split(",") if part.strip()]
    return parts


FIELD_CONVERTERS = {
    "title": lambda value: str(value).strip() or None if value is not None else None,
    "department": lambda value: str(value).strip() or None if value is not None else None,
    "requesting_team": lambda value: str(value).strip() or None if value is not None else None,
    "requester_name": lambda value: str(value).strip() or None if value is not None else None,
    "requester_email": lambda value: str(value).strip() or None if value is not None else None,
    "country": lambda value: str(value).strip() or None if value is not None else None,
    "product_area": lambda value: str(value).strip() or None if value is not None else None,
    "lifecycle_status": lambda value: str(value).strip() or None if value is not None else None,
    "customer_segment": lambda value: str(value).strip() or None if value is not None else None,
    "initiative_type": lambda value: str(value).strip() or None if value is not None else None,
    "hypothesis": lambda value: str(value).strip() or None if value is not None else None,
    "problem_statement": lambda value: str(value).strip() or None if value is not None else None,
    "active_scoring_framework": lambda value: str(value).strip() or None if value is not None else None,
    "use_math_model": _to_bool,
    "dependencies_initiatives": _split_keys,
    "dependencies_others": lambda value: str(value).strip() or None if value is not None else None,
    "llm_summary": lambda value: str(value).strip() or None if value is not None else None,
    "strategic_priority_coefficient": _to_float,
    "is_optimization_candidate": _to_bool,
    "candidate_period_key": lambda value: str(value).strip() or None if value is not None else None,
}


def backlog_row_to_update_data(row: BacklogRow) -> Dict[str, Any]:
    """Map central backlog sheet columns to Initiative fields."""
    data: Dict[str, Any] = {}

    editable_headers = {
        sheet_header: field_name
        for sheet_header, field_name in CENTRAL_HEADER_TO_FIELD.items()
        if field_name in CENTRAL_EDITABLE_FIELDS
    }

    for sheet_header, field_name in editable_headers.items():
        raw_value = get_value_by_header_alias(row, sheet_header, [])
        converter = FIELD_CONVERTERS.get(field_name, lambda value: value)
        data[field_name] = converter(raw_value)

    return data

