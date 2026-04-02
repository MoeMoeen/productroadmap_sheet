# productroadmap_sheet_project/app/services/intake_mapper.py

"""
Map a single intake sheet row (dict of column -> value) to InitiativeCreate.

Implements Step 1 from docs/flow_1.md:
- Helpers: _to_float, _to_bool, _to_date
- map_sheet_row_to_initiative_create(row)

Assumed intake sheet headers (adjust as needed):
- Title
- Department
- Requesting Team
- Requester Name
- Requester Email
- Country
- Product Area
- Problem Statement
- Deadline Date
- Lifecycle Status / Status
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.schemas.initiative import InitiativeCreate
from app.utils.header_utils import get_value_by_header_alias


def _to_float(value: Any) -> Optional[float]:
	"""Convert a cell value to float if possible, otherwise return None.

	Handles None, empty strings, numeric types, and ignores invalid text.
	"""
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
	"""Convert a cell value to bool using common truthy values.

	Recognizes: true/yes/y/1/✅/✔/ok (case-insensitive). Defaults to False.
	"""
	if isinstance(value, bool):
		return value
	if value is None:
		return False

	s = str(value).strip().lower()
	return s in {"true", "yes", "y", "1", "✅", "✔", "ok"}


def _to_date(value: Any):
	"""Convert a cell value to date if possible, otherwise return None.

	Tries to parse common formats; if Sheets/driver returns a datetime-like,
	attempts to call .date().
	"""
	if value is None:
		return None

	# If Sheets API already parsed as datetime/date:
	if hasattr(value, "date"):
		try:
			return value.date()
		except Exception:
			pass

	s = str(value).strip()
	if s == "":
		return None

	for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
		try:
			return datetime.strptime(s, fmt).date()
		except ValueError:
			continue

	return None


def _get_row_value(row: Dict[str, Any], primary_name: str, *aliases: str) -> Any:
	return get_value_by_header_alias(row, primary_name, aliases)


def _get_text(row: Dict[str, Any], primary_name: str, *aliases: str) -> Optional[str]:
	value = _get_row_value(row, primary_name, *aliases)
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def map_sheet_row_to_initiative_create(row: Dict[str, Any]) -> InitiativeCreate:
	"""Map a single Google Sheets intake row (column_name -> value)
	to an InitiativeCreate schema.

	Headers are resolved via normalized aliases, so the row may use either
	user-facing sheet headers like "Department" and "Problem Statement" or
	normalized variants like "department" and "problem_statement".

	Currently mapped intake fields include:
	- Title
	- Department
	- Requesting Team
	- Requester Name
	- Requester Email
	- Country
	- Product Area
	- Problem Statement
	- Deadline Date
	- Lifecycle Status / Status
	"""

	# Basic text fields: strip whitespace where relevant
	title = _get_text(row, "Title", "title") or ""

	return InitiativeCreate(
		# Ownership & requester
		title=title,
		department=_get_text(row, "Department", "department", "dept"),
		requesting_team=_get_text(row, "Requesting Team", "requesting_team"),
		requester_name=_get_text(row, "Requester Name", "requester_name"),
		requester_email=_get_text(row, "Requester Email", "requester_email"),
		country=_get_text(row, "Country", "country"),
		product_area=_get_text(row, "Product Area", "product_area"),

		# Problem & context
		problem_statement=_get_text(row, "Problem Statement", "problem_statement"),
		deadline_date=_to_date(_get_row_value(row, "Deadline Date", "deadline_date")),

		# Lifecycle
		lifecycle_status=(_get_text(row, "Lifecycle Status", "Lifecycle_status", "lifecycle_status", "Status", "status") or "new"),
		# active_scoring_framework left None at intake time
	)

