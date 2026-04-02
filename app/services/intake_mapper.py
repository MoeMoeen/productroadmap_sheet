# productroadmap_sheet_project/app/services/intake_mapper.py

"""
Map a single intake sheet row (dict of column -> value) to InitiativeCreate.

Implements Step 1 from docs/flow_1.md:
- Helpers: _to_float, _to_bool, _to_date
- map_sheet_row_to_initiative_create(row)

Assumed intake sheet headers (adjust as needed):
- Title
- Requesting Team
- Requester Name
- Requester Email
- Country
- Product Area
- Problem Statement
- Hypothesis
- Customer Segment
- Initiative Type
- Effort T-shirt Size
- Effort Engineering Days
- Effort Other Teams Days
- Infra Cost Estimate
- Dependencies Others
- Risk Level
- Risk Description
- Time Sensitivity
- Deadline Date
- Lifecycle Status / Status
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.schemas.initiative import InitiativeCreate


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


def map_sheet_row_to_initiative_create(row: Dict[str, Any]) -> InitiativeCreate:
	"""Map a single Google Sheets intake row (column_name -> value)
	to an InitiativeCreate schema.

	Assumes the intake sheet uses the following column headers:
	- Title
	- Requesting Team
	- Requester Name
	- Requester Email
	- Country
	- Product Area
	- Problem Statement
	- Hypothesis
	- Customer Segment
	- Initiative Type
	- Effort T-shirt Size
	- Effort Engineering Days
	- Effort Other Teams Days
	- Infra Cost Estimate
	- Dependencies Others
	- Risk Level
	- Risk Description
	- Time Sensitivity
	- Deadline Date
	- Lifecycle Status / Status
	"""

	# Basic text fields: strip whitespace where relevant
	title = (row.get("Title") or "").strip()

	return InitiativeCreate(
		# Ownership & requester
		title=title,
		department=row.get("Department") or None,
		requesting_team=row.get("Requesting Team") or None,
		requester_name=row.get("Requester Name") or None,
		requester_email=row.get("Requester Email") or None,
		country=row.get("Country") or None,
		product_area=row.get("Product Area") or None,
		market=row.get("Market") or None,
		category=row.get("Category") or None,

		# Problem & context
		problem_statement=row.get("Problem Statement") or None,
		hypothesis=row.get("Hypothesis") or None,

		# Strategic alignment & classification
		customer_segment=row.get("Customer Segment") or None,
		initiative_type=row.get("Initiative Type") or None,
		# strategic_priority_coefficient left at default 1.0

		# Effort & cost
		effort_tshirt_size=row.get("Effort T-shirt Size") or None,
		effort_engineering_days=_to_float(row.get("Effort Engineering Days")),
		effort_other_teams_days=_to_float(row.get("Effort Other Teams Days")),
		infra_cost_estimate=_to_float(row.get("Infra Cost Estimate")),
		engineering_tokens=_to_float(row.get("Engineering Tokens")),

		# Risk, dependencies, constraints
		dependencies_others=row.get("Dependencies Others") or None,
		program_key=row.get("Program Key") or None,
		risk_level=row.get("Risk Level") or None,
		risk_description=row.get("Risk Description") or None,
		time_sensitivity_score=_to_float(row.get("Time Sensitivity")),
		deadline_date=_to_date(row.get("Deadline Date")),

		# Lifecycle
		lifecycle_status=(row.get("Lifecycle Status") or row.get("Lifecycle_status") or row.get("Status") or "new").strip() or "new",
		# active_scoring_framework left None at intake time
	)

