from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.sheets.backlog_reader import BacklogRow  # type: ignore

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


def backlog_row_to_update_data(row: BacklogRow) -> Dict[str, Any]:
    """Map central backlog sheet columns to Initiative fields."""
    data: Dict[str, Any] = {}

    # High-level text fields
    data["title"] = row.get("Title") or None
    data["requesting_team"] = row.get("Requesting Team") or None
    data["country"] = row.get("Country") or None
    data["product_area"] = row.get("Product Area") or None

    data["strategic_theme"] = row.get("Strategic Theme") or None
    data["customer_segment"] = row.get("Customer Segment") or None
    data["initiative_type"] = row.get("Initiative Type") or None
    data["hypothesis"] = row.get("Hypothesis") or None

    # Linked objectives (as free text or JSON string for now)
    data["linked_objectives"] = row.get("Linked Objectives") or None

    # Scoring summary
    data["value_score"] = _to_float(row.get("Value Score"))
    data["effort_score"] = _to_float(row.get("Effort Score"))
    data["overall_score"] = _to_float(row.get("Overall Score"))

    data["active_scoring_framework"] = row.get("Active Scoring Framework") or None
    data["use_math_model"] = _to_bool(row.get("Use Math Model"))

    # Dependencies
    data["dependencies_initiatives"] = _split_keys(row.get("Dependencies Initiatives"))
    data["dependencies_others"] = row.get("Dependencies Others") or None

    # Lifecycle
    data["status"] = (row.get("Status") or "").strip() or None

    # LLM notes (summary is backend-owned)
    data["llm_notes"] = row.get("LLM Notes") or None

    # Strategic priority coefficient
    data["strategic_priority_coefficient"] = _to_float(row.get("Strategic Priority Coefficient"))

    return data

