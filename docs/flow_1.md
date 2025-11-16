
---

## Flow 1 overview (so we know where we’re going)

End-to-end, Flow 1 is:

1. Read rows from **department intake sheets** (Google Sheets).
2. Map each row → `InitiativeCreate` Pydantic model.
3. Upsert into DB as `Initiative` via `IntakeService`.
4. Regenerate **central backlog sheet** from DB.

We already have (conceptually):

* `Initiative` SQLAlchemy model (in `app/db/models/initiative.py`)
* `InitiativeCreate` Pydantic model (in `app/schemas/initiative.py`)

Now we’ll start implementing the glue.

---

# 🔹 Step 1: `intake_mapper.py` – map sheet row → `InitiativeCreate`

**Goal of this step**

Create a small, focused module that:

* Takes **one row** from an intake sheet as a `dict` (`{column_name: value}`),
* Cleans it up,
* Returns an `InitiativeCreate` object.

This lets us keep all “sheet column → internal field” logic in one place.

---

### 1.1. File & imports

**File:** `app/services/intake_mapper.py`

```python
# app/services/intake_mapper.py

from typing import Any, Dict, Optional
from datetime import datetime

from app.schemas.initiative import InitiativeCreate
```

**Explanation**

* `Dict[str, Any]` – sheet rows come as generic dicts: column name → cell value.
* `InitiativeCreate` – our Pydantic schema that defines the allowed fields and their types.

---

### 1.2. Helper converters: `_to_float` and `_to_bool` and `_to_date`

Sheets give you strings, blanks, sometimes numbers. We want robust parsing.

```python
def _to_float(value: Any) -> Optional[float]:
    """
    Convert a cell value to float if possible, otherwise return None.
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
    """
    Convert a cell value to bool using common truthy values.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False

    s = str(value).strip().lower()
    return s in {"true", "yes", "y", "1", "✅", "✔", "ok"}


def _to_date(value: Any) -> Optional[datetime.date]:
    """
    Convert a cell value to date if possible, otherwise return None.
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

    # Try common formats; you can adjust these to match your locale
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    return None
```

**Explanation**

* `_to_float`

  * Handles `None`, empty strings, and bad input gracefully → `None`.
  * Converts `int`/`float` directly.
* `_to_bool`

  * Accepts typical spreadsheet inputs (“true”, “yes”, “1”, “✅”) and normalizes to `True` or `False`.
* `_to_date`

  * Handles multiple date formats.
  * Tries to be safe and returns `None` if parsing fails.

---

### 1.3. The main mapper: `map_sheet_row_to_initiative_create`

Now we map from “sheet columns” to `InitiativeCreate` fields.

We’ll assume your **intake sheet headers** look roughly like this (you can tweak later):

* `Title`
* `Requesting Team`
* `Requester Name`
* `Requester Email`
* `Country`
* `Product Area`
* `Problem Statement`
* `Current Pain`
* `Desired Outcome`
* `Target Metrics`
* `Hypothesis`
* `Strategic Theme`
* `Customer Segment`
* `Initiative Type`
* `Expected Impact Description`
* `Impact Metric`
* `Impact Unit`
* `Impact Low`
* `Impact Expected`
* `Impact High`
* `Effort T-shirt Size`
* `Effort Engineering Days`
* `Effort Other Teams Days`
* `Infra Cost Estimate`
* `Dependencies Others`
* `Is Mandatory`
* `Risk Level`
* `Risk Description`
* `Time Sensitivity`
* `Deadline Date`
* `Status`

Here’s the mapper:

```python
def map_sheet_row_to_initiative_create(row: Dict[str, Any]) -> InitiativeCreate:
    """
    Map a single Google Sheets intake row (column_name -> value)
    to an InitiativeCreate schema.

    Assumes the intake sheet uses the following column headers:
    - Title
    - Requesting Team
    - Requester Name
    - Requester Email
    - Country
    - Product Area
    - Problem Statement
    - Current Pain
    - Desired Outcome
    - Target Metrics
    - Hypothesis
    - Strategic Theme
    - Customer Segment
    - Initiative Type
    - Expected Impact Description
    - Impact Metric
    - Impact Unit
    - Impact Low
    - Impact Expected
    - Impact High
    - Effort T-shirt Size
    - Effort Engineering Days
    - Effort Other Teams Days
    - Infra Cost Estimate
    - Dependencies Others
    - Is Mandatory
    - Risk Level
    - Risk Description
    - Time Sensitivity
    - Deadline Date
    - Status
    """

    # Basic text fields: strip whitespace where relevant
    title = (row.get("Title") or "").strip()

    return InitiativeCreate(
        # Ownership & requester
        title=title,
        requesting_team=row.get("Requesting Team") or None,
        requester_name=row.get("Requester Name") or None,
        requester_email=row.get("Requester Email") or None,
        country=row.get("Country") or None,
        product_area=row.get("Product Area") or None,

        # Problem & context
        problem_statement=row.get("Problem Statement") or None,
        current_pain=row.get("Current Pain") or None,
        desired_outcome=row.get("Desired Outcome") or None,
        target_metrics=row.get("Target Metrics") or None,
        hypothesis=row.get("Hypothesis") or None,

        # Strategic alignment & classification
        strategic_theme=row.get("Strategic Theme") or None,
        customer_segment=row.get("Customer Segment") or None,
        initiative_type=row.get("Initiative Type") or None,
        # strategic_priority_coefficient left at default 1.0

        # Impact & value modeling
        expected_impact_description=row.get("Expected Impact Description") or None,
        impact_metric=row.get("Impact Metric") or None,
        impact_unit=row.get("Impact Unit") or None,
        impact_low=_to_float(row.get("Impact Low")),
        impact_expected=_to_float(row.get("Impact Expected")),
        impact_high=_to_float(row.get("Impact High")),

        # Effort & cost
        effort_tshirt_size=row.get("Effort T-shirt Size") or None,
        effort_engineering_days=_to_float(row.get("Effort Engineering Days")),
        effort_other_teams_days=_to_float(row.get("Effort Other Teams Days")),
        infra_cost_estimate=_to_float(row.get("Infra Cost Estimate")),
        # total_cost_estimate left empty; derived later

        # Risk, dependencies, constraints
        dependencies_others=row.get("Dependencies Others") or None,
        is_mandatory=_to_bool(row.get("Is Mandatory")),
        risk_level=row.get("Risk Level") or None,
        risk_description=row.get("Risk Description") or None,
        time_sensitivity=row.get("Time Sensitivity") or None,
        deadline_date=_to_date(row.get("Deadline Date")),

        # Lifecycle
        status=(row.get("Status") or "new").strip() or "new",
        # active_scoring_framework left None at intake time
    )
```

**Explanation (field by field)**

* `title`:

  * We force `Title` to a non-empty string (could be empty if sheet row broken, but Pydantic will catch if you make it required).
* For text fields (`requesting_team`, `country`, etc.):

  * Use `row.get("…") or None` so empty cells become `None`, not empty strings.
* For numbers (impact/effort/cost):

  * Use `_to_float` to handle `None`, `""`, `"  "`, invalid text, etc.
* `is_mandatory`:

  * `_to_bool` interprets `"yes"`, `"TRUE"`, `"1"`, `✅`, etc. as `True`.
* `deadline_date`:

  * `_to_date` tries several formats and returns a `date` or `None`.
* `status`:

  * Use sheet value if present, otherwise `"new"`.

---

At this point we have:

* A robust, centralized mapping from intake sheet rows → internal schema.
* All raw ugliness of Sheets contained in `intake_mapper.py`.
* `InitiateCreate` object that we can safely pass into `IntakeService`.

---
# 🔹 Step 2: `IntakeService`

Perfect, let’s wire up **Step 2: `IntakeService`** properly, taking into account:

* `dependencies_initiatives` is *not* set from intake.
* `InitiativeCreate` already includes extra fields (linked objectives, scores, LLM stuff) that are **not** coming from intake.
* People might use formulas in sheets → we assume the **reader** gives us evaluated values, not formula strings.

I’ll show you one self-contained file:

* `app/services/intake_service.py`

and annotate it so you can drop it into your repo.

---

## `app/services/intake_service.py`

```python
# app/services/intake_service.py

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.schemas.initiative import InitiativeCreate
from app.services.initiative_key import generate_initiative_key
from app.services.intake_reader import IntakeRow  # we'll define this type alias in your reader
from app.services.intake_mapper import map_row_to_initiative_create
```

> 🔎 **Note:** I’m assuming you’ll have something like an `IntakeRow = Dict[str, Any]` (or a small dataclass) in `intake_reader.py`. 

---

### 1️⃣ Define which fields are allowed to be updated from the *intake* side

We do **not** want an intake sync to overwrite product-owned / backend-owned fields (scores, LLM notes, etc.).

```python
# Fields that are allowed to be written/updated from department intake sheets.
# Everything else in InitiativeBase/InitiativeCreate should be left to product/LLM/backend.
INTAKE_EDITABLE_FIELDS = {
    # Ownership & requester
    "title",
    "requesting_team",
    "requester_name",
    "requester_email",
    "country",
    "product_area",

    # Problem & context
    "problem_statement",
    "current_pain",
    "desired_outcome",
    "target_metrics",
    "hypothesis",

    # Strategic alignment (what requesters / BUs might fill)
    "strategic_theme",
    "customer_segment",
    "initiative_type",

    # Impact & value (high level)
    "expected_impact_description",
    "impact_metric",
    "impact_unit",
    "impact_low",
    "impact_expected",
    "impact_high",

    # Effort & cost (as provided by teams)
    "effort_tshirt_size",
    "effort_engineering_days",
    "effort_other_teams_days",
    "infra_cost_estimate",
    # total_cost_estimate is derived / product-owned → not updated from intake

    # Dependencies / risk
    "dependencies_others",
    "is_mandatory",
    "risk_level",
    "risk_description",
    "time_sensitivity",
    "deadline_date",

    # Status: intake side can set/override some values (e.g. new / withdrawn)
    # Product may further update it via other flows; we can add guards later.
    "status",
}
```

> 🧠 **Why this filter?** It prevents a later intake edit from accidentally wiping out things like `linked_objectives`, `dependencies_initiatives`, `value_score`, `llm_notes`, etc., which are not owned by the requesters.

---

### 2️⃣ The `IntakeService` class skeleton

```python
class IntakeService:
    """
    Service responsible for transforming intake sheet rows into Initiative
    records in the database.

    Key responsibilities:
    - Map raw sheet rows -> InitiativeCreate (via map_row_to_initiative_create).
    - Upsert into `initiatives` table.
    - Respect ownership of fields (only update intake-owned fields).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
```

---

### 3️⃣ Public entrypoint: `upsert_from_intake_row`

This is what your `sync_intake_job.py` will call for each row.

```python
    def upsert_from_intake_row(
        self,
        row: Dict[str, Any],
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
    ) -> Initiative:
        """
        Upsert an Initiative based on a single intake sheet row.

        - `row` is a dict of column_name -> evaluated value (NOT formula).
        - `source_*` fields come from the intake reader (sheet metadata).
        """
        # 1) Map the raw row into a validated Pydantic model.
        dto: InitiativeCreate = map_row_to_initiative_create(row)

        # 2) Try to find an existing initiative:
        #    a) Prefer matching by initiative_key (if the sheet has it as a read-only column),
        #    b) otherwise fall back to (sheet_id, tab_name, row_number).
        initiative = self._find_existing_initiative(row, source_sheet_id, source_tab_name, source_row_number)

        if initiative is None:
            initiative = self._create_from_intake(dto, source_sheet_id, source_tab_name, source_row_number)
        else:
            self._apply_intake_update(initiative, dto)

        self.db.commit()
        self.db.refresh(initiative)
        return initiative
```

---

### 4️⃣ Finding an existing initiative

We try by `initiative_key` first (if the intake sheet has a read-only “Initiative Key” column), then fallback to the physical row identity.

```python
    def _find_existing_initiative(
        self,
        row: Dict[str, Any],
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
    ) -> Optional[Initiative]:
        """
        Try to find an existing initiative for this intake row.

        Strategy:
        - If the row contains a non-empty 'initiative_key' column, match on that.
        - Else, match on (source_sheet_id, source_tab_name, source_row_number).
        """

        # a) Try to use initiative_key if present in the sheet as a read-only column.
        init_key = None
        for key in ("initiative_key", "Initiative Key", "initiative_key".upper()):
            if key in row and row[key]:
                init_key = str(row[key]).strip()
                break

        if init_key:
            existing = (
                self.db.query(Ini tiative)
                .filter(Initiative.initiative_key == init_key)
                .one_or_none()
            )
            if existing is not None:
                return existing

        # b) Fallback: use the sheet + tab + row number as the legacy identity.
        return (
            self.db.query(Initiative)
            .filter(
                Initiative.source_sheet_id == source_sheet_id,
                Initiative.source_tab_name == source_tab_name,
                Initiative.source_row_number == source_row_number,
            )
            .one_or_none()
        )
```

> 📝 **Note:** Once you put `initiative_key` as a read-only column on the intake sheet, future edits to that row will always hit the same DB record, even if the row moves.

---

### 5️⃣ Creating a new `Initiative` from intake

```python
    def _create_from_intake(
        self,
        dto: InitiativeCreate,
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
    ) -> Initiative:
        """
        Create a brand-new Initiative from an intake DTO.
        """
        # Generate a new human-friendly key (e.g. "INIT-2025-001")
        initiative_key = generate_initiative_key(self.db)

        initiative = Initiative(
            # Identity / source
            initiative_key=initiative_key,
            source_sheet_id=source_sheet_id,
            source_tab_name=source_tab_name,
            source_row_number=source_row_number,
            # All fields from the DTO (Pydantic will have set defaults for omitted ones)
            **dto.model_dump(),
        )

        self.db.add(initiative)
        return initiative
```

> 🔐 **Ownership reminder:** At this point, fields like `linked_objectives`, `dependencies_initiatives`, `value_score`, `llm_notes`, etc. are all just their default values from `InitiativeBase`. They’re in the DB but still `None` / default and will be filled by other flows.

---

### 6️⃣ Updating an existing `Initiative` from intake

We only touch the **intake-owned fields**.

```python
    def _apply_intake_update(self, initiative: Initiative, dto: InitiativeCreate) -> None:
        """
        Update an existing Initiative with data from an intake DTO,
        but only for fields that are owned by the intake side.

        This protects product/LLM-owned fields from being overwritten
        by department edits.
        """
        data = dto.model_dump(exclude_unset=True)

        for field_name, value in data.items():
            if field_name not in INTAKE_EDITABLE_FIELDS:
                # Skip fields that should not be mutated from intake sheets.
                continue

            # Special case: you *might* want to restrict which status values
            # intake users are allowed to set (e.g. only 'new' or 'withdrawn').
            if field_name == "status":
                # Simple example: clamp to allowed intake statuses
                allowed_from_intake = {"new", "withdrawn"}
                if value not in allowed_from_intake:
                    # Ignore disallowed statuses from intake; keep existing
                    continue

            setattr(initiative, field_name, value)
```

> 🧷 **Where do central-only fields come from?**
> Later, when we implement the **central backlog sync**, we’ll have another service (e.g. `CentralBacklogService`) that can update `linked_objectives`, `dependencies_initiatives`, `active_scoring_framework`, `value_score`, `llm_notes`, etc. That service will have its own `CENTRAL_EDITABLE_FIELDS` set, separate from intake.

---

## 4️⃣ Quick recap of how this fits into the bigger picture

* **Intake flow (what we’re doing now):**

  1. `intake_reader` reads department sheets with `valueRenderOption="UNFORMATTED_VALUE"` → you get evaluated values even if users used formulas.
  2. For each row:

     * `map_row_to_initiative_create(row)` builds an `InitiativeCreate` (your `InitiativeBase` + defaults).
     * `IntakeService.upsert_from_intake_row(...)` creates or updates the `Initiative` in DB, respecting field ownership.

* **Central backlog flow (later):**

  * Another service + mapper reads/writes more fields (objectives, dependencies_initiatives, scoring, LLM notes) from/to the central sheet and the same `Initiative` records.

* **Scoring / LLM / optimization flows (later):**

  * Operate on the same `Initiative` row, updating scoring fields, math_model links, etc.

So we’re keeping the responsibilities clean:

* Intake just populates what the departments *own*.
* Product, LLM, and optimization add layers on top via other services.

---

