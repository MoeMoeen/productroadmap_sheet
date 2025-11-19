sheet to db:
- readers read rows from sheets
- service write them into db

db to sheets:
- sync jobs (?) (sync is 2 way)
- writers write rows into sheets


**backlog_sync_job vs backlog_update_job**

backlog_sync_job (DB → Sheet)

    Purpose: Regenerates the central backlog sheet from the database.
    What it does: Reads all Initiatives from DB and writes the sheet (header + rows) in the canonical order/format.
    When to run: After DB changes (e.g., after intake sync, scoring updates, or product edits accepted) to publish the current DB truth out to the central sheet.

backlog_update_job (Sheet → DB)

    Purpose: Applies edits made in the central backlog sheet back into the DB.
    What it does: Reads central sheet rows, finds initiatives by Initiative Key, and updates only product-owned fields (CENTRAL_EDITABLE_FIELDS).
    When to run: Before a sync or on a schedule (e.g., regularly ingest product edits). Typically: run this first (pull product edits into DB), then run backlog_sync_job (push the unified DB truth back out).

Tip on orchestration:

    Typical cycle:
        Intake sync (dept sheets → DB + keys from DB → dept sheets)
        Backlog update (central edits → DB)
        Backlog sync (DB → central backlog)

    This avoids a “flip-flop” where product edits get overwritten by a write from the DB that didn’t include their changes yet.

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

# 🔹 Step 3: `Intake Reader: Google Sheets → intake rows + Backlog Writer: DB → Central Backlog Sheet `

Nice, let’s wire the Google Sheets side in properly 🧩

We’ll do:

* **3A – `intake_reader`: Sheets → row dicts**
* **3B – `backlog_writer`: DB → central backlog sheet**

I’ll assume:

* You’ll later plug real Google auth into `client.py`.
* We only care about **evaluated values**, not formulas.

---

## 3A – Intake Reader: Google Sheets → intake rows

### 3A.1. Sheets client abstraction

**File:** `app/sheets/client.py`

This is a thin wrapper around the actual Google Sheets API client. For now we keep it minimal but realistic.

```python
# app/sheets/client.py

from typing import List, Any

# You will later import the real Google API client here
# from googleapiclient.discovery import build
# from google.oauth2.service_account import Credentials


class SheetsClient:
    """
    Thin wrapper around Google Sheets API.

    Responsible for:
    - Reading values from a given sheet & range.
    - Writing values to a given sheet & range.

    We assume it returns evaluated values (not formulas).
    """

    def __init__(self, service) -> None:
        """
        `service` is the Google Sheets service object created via googleapiclient.
        We'll treat it as an opaque dependency here.
        """
        self.service = service

    def get_values(
        self,
        spreadsheet_id: str,
        range_: str,
        value_render_option: str = "UNFORMATTED_VALUE",
    ) -> List[List[Any]]:
        """
        Read a 2D range of values from a sheet.

        Returns a list of rows, each row is a list of cell values.
        Missing/empty cells come back as empty strings.
        """
        resp = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueRenderOption=value_render_option,
            )
            .execute()
        )
        return resp.get("values", [])

    def update_values(
        self,
        spreadsheet_id: str,
        range_: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> None:
        """
        Write a 2D range of values to a sheet.

        `values` should include the header row if you want to rewrite it.
        """
        body = {"values": values}
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_,
                valueInputOption=value_input_option,
                body=body,
            )
            .execute()
        )
```

**Key points:**

* `valueRenderOption="UNFORMATTED_VALUE"` means:

  * If a cell has a formula `=B2 * 0.2`, we get the **evaluated numeric result**, which is exactly what we want for intake.
* `update_values` uses `"USER_ENTERED"`, so if we push formulas later, Sheets will treat them as formulas; for our central backlog we’ll mostly push plain values.

---

### 3A.2. Intake reader: turn sheet → list of row dicts

**File:** `app/sheets/intake_reader.py`

```python
# app/sheets/intake_reader.py

from typing import Any, Dict, Iterable, List, Tuple

from app.sheets.client import SheetsClient

# Type alias for clarity: (row_number, row_dict)
IntakeRow = Tuple[int, Dict[str, Any]]


class IntakeReader:
    """
    Reads department intake sheets and returns rows as (row_number, dict) pairs.

    Assumes:
    - Row 1 contains the header names.
    - Rows 2..N contain data.
    - We want evaluated cell values (not formulas).
    """

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows_for_sheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        header_row: int = 1,
        start_data_row: int = 2,
        max_rows: int = 1000,  # just a soft default
    ) -> List[IntakeRow]:
        """
        Read all intake rows from a given sheet/tab.

        Returns a list of (row_number, row_dict) tuples.
        """
        # Build A1-style range: e.g. "Intake!A1:Z1000"
        # You can widen the column range if you add more columns.
        range_ = f"{tab_name}!A{header_row}:Z{header_row + max_rows}"

        raw_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=range_,
            value_render_option="UNFORMATTED_VALUE",
        )

        if not raw_values:
            return []

        # First row is the header
        header = raw_values[0]
        data_rows = raw_values[1:]

        rows: List[IntakeRow] = []
        current_row_number = start_data_row

        for row_cells in data_rows:
            # Skip entirely empty rows
            if self._is_empty_row(row_cells):
                current_row_number += 1
                continue

            row_dict = self._row_to_dict(header, row_cells)
            rows.append((current_row_number, row_dict))
            current_row_number += 1

        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> Dict[str, Any]:
        """
        Map a list of cell values into a dict based on header names.
        Extra header cells beyond the row are ignored; missing cells become "".
        """
        row_dict: Dict[str, Any] = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue  # ignore blank header columns

            value = row_cells[idx] if idx < len(row_cells) else ""
            row_dict[key] = value
        return row_dict

    def _is_empty_row(self, row_cells: Iterable[Any]) -> bool:
        """
        Consider a row empty if all cells are None or empty string.
        """
        for cell in row_cells:
            if cell not in (None, ""):
                return False
        return True
```

**What this does:**

* Reads `A1:Z1000` (you can widen later) from a tab like `"UK_Sales_Intake"`.
* Treats the **first row** as headers.
* Converts each subsequent row into:

  * `row_number` (the real sheet row index),
  * `row_dict` mapping `"Title" → "Improve Checkout"`, etc.
* Skips fully-empty rows.
* Always returns **evaluated values** (formulas → numbers/strings).

**How it’s used by the job:**

```python
# app/jobs/sync_intake_job.py (sketch)
from app.db.session import SessionLocal
from app.sheets.client import SheetsClient
from app.sheets.intake_reader import IntakeReader
from app.services.intake_service import IntakeService

def run_sync_for_sheet(spreadsheet_id: str, tab_name: str, sheets_service) -> None:
    db = SessionLocal()
    try:
        client = SheetsClient(sheets_service)
        reader = IntakeReader(client)
        service = IntakeService(db)

        for row_number, row_dict in reader.get_rows_for_sheet(spreadsheet_id, tab_name):
            service.upsert_from_intake_row(
                row=row_dict,
                source_sheet_id=spreadsheet_id,
                source_tab_name=tab_name,
                source_row_number=row_number,
            )
    finally:
        db.close()
```

So where does the list-of-lists turn into that dict?
**Answer: in the `IntakeReader`.** `SheetsClient` is *low-level plumbing*; `IntakeReader` is the adapter that builds `IntakeRow` dictionaries for `IntakeService`.

Let me walk you through the full pipeline with concrete code + an example.

---

## 1. Roles of each piece

### `SheetsClient` – low-level grid I/O

* Talks to Google’s API.
* Knows nothing about your domain.
* Just reads/writes “a rectangle of cells”.

```python
values = sheets_client.get_values(
    spreadsheet_id="...", 
    range_="Intake!A1:Z1000"
)
# values is like:
# [
#   ["Title", "Requesting Team", "Requester Name", ...],   # header row
#   ["Improve checkout", "Sales", "Alice", ...],           # row 2
#   ["New pricing page", "Marketing", "Bob", ...],         # row 3
#   ...
# ]
```

It’s intentionally **dumb**: it returns “rows of cells”.

### `IntakeReader` – converts rows → `Dict` objects

`IntakeReader` sits **on top of** `SheetsClient` and is the thing that:

1. Calls `get_values`.
2. Takes the **first row as the header**.
3. For each subsequent row, builds a dict: `{ "Title": "Improve checkout", "Requesting Team": "Sales", ... }`.
4. Returns `(row_number, row_dict)` pairs.

So `IntakeReader` is what gives you an `IntakeRow` (`Dict[str, Any]`), not `SheetsClient`.

The code we sketched (slightly re-labeled to match your naming):

```python
# app/sheets/intake_reader.py

from typing import Dict, Any, List, Tuple
from app.sheets.client import SheetsClient

IntakeRow = Dict[str, Any]

class IntakeReader:
    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows_for_sheet(
        self,
        sheet_id: str,
        tab_name: str,
    ) -> List[Tuple[int, IntakeRow]]:
        values = self.client.get_values(
            spreadsheet_id=sheet_id,
            range_=f"{tab_name}!A1:Z1000"
        )
        if not values:
            return []

        header = values[0]                  # ["Title", "Requesting Team", ...]
        data_rows = values[1:]              # subsequent rows
        rows: List[Tuple[int, IntakeRow]] = []

        for idx, row in enumerate(data rows, start=2):  # row 2,3,4...
            if self._is_empty(row):
                continue
            row_dict: IntakeRow = self._to_dict(header, row)
            rows.push((idx, row_dict))      # (row_number, dict)

        return rows

    def _to_dict(self, header: List[Any], row: List[Any]) -> IntakeRow:
        d: IntakeRow = {}
        for col_index, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue
            d[key] = row[col_index] if col_index < len(row) else ""
        return d

    def _is_empty(self, row: List[Any]) -> bool:
        return all((cell is None or cell == "") for cell in row)
```

So **`IntakeReader` is the thing that produces `IntakeRow`** in the shape `Dict[str, Any]`.

### `IntakeService` – takes a logical row, not a grid

Now `IntakeService.upsert_from_intake_row` is not supposed to know about grids, ranges, or Google API. It only cares about *business-level* records:

```python
# app/services/intake_service.py

class IntakeService:
    def __init__(self, db: Session, key_writer: Optional[InitiativeKeyWriter] = None):
        self.db = db
        self.key_writer = key_writer

    def upsert_from_intake_row(
        self,
        row: IntakeRow,  # <-- this is the dict coming from IntakeReader, not SheetsClient directly
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
        allow_status_override: bool = False,
    ) -> Initiative:
        dto: InitiativeCreate = map_sheet_row_to_initiative_create(row)
        ...
```

So the flow is:

1. `SheetsClient.get_values` gives raw `List[List[Any]]`.
2. `IntakeReader.get_rows_for_sheet` converts to `(row_number, IntakeRow)` where `IntakeRow = Dict[str, Any>`.
3. The **job** calls `IntakeService.upsert_from_intake_row(...)` with that `row_dict`.

---

## 2. Full call chain: from Google Sheet to DB

Let’s put all the pieces together.

### Step 1: low-level read

```python
# inside IntakeReader.get_rows_for_sheet
values = sheets_client.get_values("sheet_id", "Intake!A1:Z1000")

# Example:
values = [
    ["Title", "Requesting Team", "Requester Name"],
    ["Improve checkout", "Sales", "Alice"],
    ["New pricing",       "Marketing", "Bob"],
]
```

### Step 2: convert to IntakeRow dicts

`IntakeReader` uses the header row to build dicts:

* For row 2, `row_dict = {"Title": "Improve checkout", "Requesting Team": "Sales", "Requester Name": "Alice"}`
* For row 3, `row_dict = {"Title": "New pricing", "Requesting Team": "Marketing", "Requester Name": "Bob"}`

So now `get_rows_for_sheet` returns:

```python
[
  (2, {"Title": "Improve checkout", "Requesting Team": "Sales", "Requester Name": "Alice"}),
  (3, {"Title": "New pricing", "Requesting Team": "Marketing", "Requester Name": "Bob"}),
]
```

Those `{"Title": ..., "Requesting Team": ...}` dicts are exactly your `IntakeRow`.

### Step 3: the job wires `IntakeReader` → `IntakeService`

Your sync job looks like:

```python
# app/jobs/sync_intake_job.py
from app.sheets.client import SheetsClient
from app.sheets.intake_reader import IntakeReader
from app.services.intake_service import IntakeService
from app.db.session import SessionLocal

def run_sync_for_intake_sheet(sheet_id: str, tab_name: str, google_service) -> None:
    db = SessionLocal()
    try:
        sheets_client = SheetsClient(google_service)
        reader = IntakeReader(sheets_client)
        intake_service = IntakeService(db, key_writer=...)  # optional

        for row_number, row_dict in reader.get_rows_for_sheet(sheet_id, tab_name):
            intake_service.upsert_from_intake_row(
                row=row_dict,
                source_sheet_id=sheet_id,
                source_tab_name=tab_name,
                source_row_number=row_number,
            )
    finally:
        db.close()
```

So:

* The job uses `SheetsClient` only via `IntakeReader`.
* `IntakeService` never touches `SheetsClient` directly.

---

## 3. What about `key_writer` / `_backfill_initiative_key`?

You also have this bit:

```python
key_val = getattr(initiative, "initiative_key", None)
if key_val:
    self._backfill_initiative_key(
        source_sheet_id, source_tab_name, source_row_number, str(key_val)
    )
```

This is about the **reverse direction**: once you generate an `initiative_key` in the DB, you want to write it back into the intake row in Sheets so it becomes visible and persistent.

The idea is:

* `InitiativeKeyWriter` is a thin adapter wrapping `SheetsClient` that knows:

  * The column index or column name where `initiative_key` should be written.
  * The logic to build the right A1 notation for `(sheet_id, tab_name, row_number, column "Initiative Key")`.

It might look roughly like:

```python
# app/sheets/key_writer.py
class InitiativeKeyWriter:
    def __init__(self, client: SheetsClient, key_column_letter: str = "A"):
        self.client = client
        self.key_column_letter = key_column_letter

    def write_key(self, sheet_id: str, tab_name: str, row_number: int, key: str) -> None:
        cell_range = f"{tab_name}!{self.key_column_letter}{row_number}"
        self.client.update_values(
            spreadsheet_id=sheet_id,
            range_=cell_range,
            # update_values expects a 2D list
            values=[[key]],
        )
```

Then in `IntakeService._backfill_initiative_key`:

```python
def _backfill_initiative_key(self, sheet_id, tab_name, row_number, key):
    if not self.key_writer:
        return
    self.key_writer.write_key(sheet_id, tab_name, row_number, key)
```

So again:

* `IntakeService` doesn’t talk to `SheetsClient` directly.
* It calls `key_writer`, which *internally* uses `SheetsClient.update_values`.

---

## 4. So what is `SheetsClient` **really**?

Think of `SheetsClient` as:

> “My low-level HTTP client to Google Sheets, returning grids of values.”

You almost never call `get_values` or `update_values` from your domain services directly. You always wrap it in a more domain-aware adapter:

* `IntakeReader` → builds `IntakeRow` dicts.
* `BacklogReader` / `BacklogWriter` → know about `initiative_key`, `value_score`, etc.
* `InitiativeKeyWriter` → knows which column is the key.
* `MathModelsReader` / `MathParamsReader` → know about `param_name`, `value`, etc.

Your **domain services** (`IntakeService`, `ScoringService`, `RoadmapService`) work with:

* `Dict`s,
* Pydantic models,
* ORM objects,

not with raw `List[List[Any]]`.

---

## 3B – Backlog Writer: DB → Central Backlog Sheet

Now we do the reverse: take all `Initiative` rows from DB and materialize the **central backlog sheet**.

### 3B.1. Decide the central backlog columns

For now, let’s define a **minimal but useful** central backlog schema (you can extend later):

Columns:

1. `Initiative Key`
2. `Title`
3. `Requesting Team`
4. `Requester Name`
5. `Requester Email`
6. `Country`
7. `Product Area`
8. `Status`
9. `Strategic Theme`
10. `Customer Segment`
11. `Initiative Type`
12. `Hypothesis`
13. `Value Score`
14. `Effort Score`
15. `Overall Score`
16. `Active Scoring Framework`
17. `Use Math Model`
18. `Dependencies Initiatives` (comma-separated keys)
19. `Dependencies Others`
20. `LLM Summary`
21. `LLM Notes`
22. `Strategic Priority Coefficient`

We can add more later (impact fields, etc.), but this is enough to show the pattern.

Let’s centralize the header in one place.

```python
# app/sheets/backlog_writer.py

from typing import Any, List, Dict

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.client import SheetsClient


CENTRAL_BACKLOG_HEADER = [
    "Initiative Key",
    "Title",
    "Requesting Team",
    "Requester Name",
    "Requester Email",
    "Country",
    "Product Area",
    "Status",
    "Strategic Theme",
    "Customer Segment",
    "Initiative Type",
    "Hypothesis",
    "Value Score",
    "Effort Score",
    "Overall Score",
    "Active Scoring Framework",
    "Use Math Model",
    "Dependencies Initiatives",
    "Dependencies Others",
    "LLM Summary",
    "LLM Notes",
    "Strategic Priority Coefficient",
]
```

---

### 3B.2. Map `Initiative` → row list

We define a helper that turns one ORM object into a list of cell values in the correct order.

```python
def initiative_to_backlog_row(initiative: Initiative) -> List[Any]:
    """
    Convert an Initiative ORM object into a list of cell values
    matching CENTRAL_BACKLOG_HEADER order.
    """

    # dependencies_initiatives is a list of initiative_keys in your Pydantic/DB
    deps_inits = ""
    if initiative.dependencies_initiatives:
        # join as comma-separated string: "INIT-000123, INIT-000150"
        deps_inits = ", ".join(initiative.dependencies_initiatives)

    return [
        initiative.initiative_key,
        initiative.title,
        initiative.requesting_team,
        initiative.requester_name,
        initiative.requester_email,
        initiative.country,
        initiative.product_area,
        initiative.status,
        initiative.strategic_theme,
        initiative.customer_segment,
        initiative.initiative_type,
        initiative.hypothesis,
        initiative.value_score,
        initiative.effort_score,
        initiative.overall_score,
        initiative.active_scoring_framework,
        initiative.use_math_model,
        deps_inits,
        initiative.dependencies_others,
        initiative.llm_summary,
        initiative.llm_notes,
        initiative.strategic_priority_coefficient,
    ]
```

---

### 3B.3. Writer function: DB → central backlog sheet

```python
def write_backlog_from_db(
    db: Session,
    client: SheetsClient,
    backlog_spreadsheet_id: str,
    backlog_tab_name: str = "Backlog",
) -> None:
    """
    Regenerate the central backlog sheet from the Initiatives table.

    Strategy:
    - Query all initiatives (you can later filter by org, status, etc.).
    - Build rows using `initiative_to_backlog_row`.
    - Write header + rows to the sheet range, overwriting previous content.
    """

    # 1) Query all initiatives
    initiatives: List[Initiative] = db.query(Initiative).order_by(Initiative.id).all()

    # 2) Build 2D values array: [header, row1, row2, ...]
    values: List[List[Any]] = []
    values.append(CENTRAL_BACKLOG_HEADER)

    for initiative in initiatives:
        values.append(initiative_to_backlog_row(initiative))

    # 3) Compute range: e.g. "Backlog!A1:W1000" (22 columns → W)
    #    We can just start at A1; Sheets will size the range automatically.
    start_cell = "A1"
    # We'll just specify the starting cell; update_values will overwrite as needed.
    range_ = f"{backlog_tab_name}!{start_cell}"

    client.update_values(
        spreadsheet_id=backlog_spreadsheet_id,
        range_=range_,
        values=values,
        value_input_option="USER_ENTERED",
    )
```

**What this does:**

* Pulls *all* `Initiative` rows from DB.
* Builds a big `[header] + rows` matrix.
* Writes it starting at `Backlog!A1` (Sheets will clear neighbor cells in that range).
* Exposes all the fields we care about for central view.

You can later:

* Add more columns to `CENTRAL_BACKLOG_HEADER` + `initiative_to_backlog_row`.
* Filter which initiatives are shown (e.g. exclude `status="rejected"`).
* Add formatting/conditional-formatting via the Sheets API if you want to get fancy.

---

### 3B.4. How it fits in a job

**File:** `app/jobs/backlog_sync_job.py` (you can name it as you like)

```python
# app/jobs/backlog_sync_job.py

from app.db.session import SessionLocal
from app.sheets.client import SheetsClient
from app.sheets.backlog_writer import write_backlog_from_db

def run_backlog_sync(backlog_spreadsheet_id: str, sheets_service) -> None:
    """
    Regenerate central backlog from DB.
    """
    db = SessionLocal()
    try:
        client = SheetsClient(sheets_service)
        write_backlog_from_db(
            db=db,
            client=client,
            backlog_spreadsheet_id=backlog_spreadsheet_id,
            backlog_tab_name="Backlog",
        )
    finally:
        db.close()
```

You can:

* Run this after each intake sync.
* Or on a schedule (e.g. every 10 minutes).
* Or expose an API/CLI command to trigger manually.

---

## Quick recap

You now have:

### 3A – Intake Reader

* `SheetsClient.get_values()` → **evaluated** values from Google Sheets.
* `IntakeReader.get_rows_for_sheet()`:

  * Treats row 1 as header.
  * Returns `[(row_number, row_dict), …]`.

### 3B – Backlog Writer

* `initiative_to_backlog_row()` to map ORM objects to sheet rows.
* `write_backlog_from_db()` to regenerate the central backlog sheet from DB.

These two plus `IntakeService` complete **Flow 1: Intake → Backlog**:

1. Intake sheets → `IntakeReader` → `IntakeService` → DB.
2. DB → `backlog_writer` → central backlog sheet.


# 🔹 Step 4: `BacklogReader + BacklogService`

We’ll mirror what we did for intake, but with a **different ownership model**:

* `BacklogReader` turns the **central backlog sheet grid** into `BacklogRow` dicts.
* `BacklogService.update_from_central_row`:

  * finds the right `Initiative` by `initiative_key`,
  * applies only **product-owned fields** (linked_objectives, dependencies_initiatives, scoring knobs, etc.),
  * leaves intake-owned + backend-owned fields untouched.

I’ll show:

1. `BacklogReader` (`app/sheets/backlog_reader.py`)
2. `BacklogService` (`app/services/backlog_service.py`)

---

## 1. BacklogReader – central sheet → BacklogRow dict

Very similar pattern to `IntakeReader`, just logically for the central backlog.

### 1.1. Type alias & class

**File:** `app/sheets/backlog_reader.py`

```python
# app/sheets/backlog_reader.py

from typing import Any, Dict, List, Tuple

from app.sheets.client import SheetsClient

BacklogRow = Dict[str, Any]


class BacklogReader:
    """
    Reads the central backlog sheet and returns rows as (row_number, dict) pairs.

    Assumes:
    - Row 1 contains header names (same we used when writing the backlog).
    - Rows 2..N contain data.
    - We want evaluated cell values (not formulas).
    """

    def __init__(self, client: SheetsClient) -> None:
        self.client = client

    def get_rows(
        self,
        spreadsheet_id: str,
        tab_name: str = "Backlog",
        header_row: int = 1,
        start_data_row: int = 2,
        max_rows: int = 5000,
    ) -> List[Tuple[int, BacklogRow]]:
        """
        Read all backlog rows from the given sheet/tab.

        Returns a list of (row_number, row_dict).
        """
        range_ = f"{tab_name}!A{header_row}:ZZ{header_row + max_rows}"

        raw_values = self.client.get_values(
            spreadsheet_id=spreadsheet_id,
            range_=range_,
            value_render_option="UNFORMATTED_VALUE",
        )

        if not raw_values:
            return []

        header = raw_values[0]
        data_rows = raw_values[1:]

        rows: List[Tuple[int, BacklogRow]] = []
        row_number = start_data_row

        for row_cells in data_rows:
            if self._is_empty_row(row_cells):
                row_number += 1
                continue

            row_dict = self._row_to_dict(header, row_cells)

            # If there's no Initiative Key, we skip (cannot map to DB)
            init_key = self._extract_initiative_key(row_dict)
            if not init_key:
                row_number += 1
                continue

            rows.append((row_number, row_dict))
            row_number += 1

        return rows

    def _row_to_dict(self, header: List[Any], row_cells: List[Any]) -> BacklogRow:
        row_dict: BacklogRow = {}
        for idx, col_name in enumerate(header):
            key = str(col_name).strip()
            if not key:
                continue
            value = row_cells[idx] if idx < len(row_cells) else ""
            row_dict[key] = value
        return row_dict

    def _is_empty_row(self, row_cells: List[Any]) -> bool:
        return all(cell in (None, "") for cell in row_cells)

    def _extract_initiative_key(self, row: BacklogRow) -> str:
        for candidate in ("Initiative Key", "initiative_key", "INITIATIVE_KEY"):
            if candidate in row and row[candidate]:
                return str(row[candidate]).strip()
        return ""
```

**What this gives you:**

* For each non-empty row with an `Initiative Key`, you get:

```python
(row_number, {
    "Initiative Key": "INIT-000123",
    "Title": "Improve checkout",
    "Strategic Theme": "Growth",
    "Active Scoring Framework": "RICE",
    "Dependencies Initiatives": "INIT-000050, INIT-000051",
    ...
})
```

This `BacklogRow` dict is what we’ll feed into `BacklogService.update_from_central_row`.

---

## 2. BacklogService – update product-owned fields from central sheet

Now we design a service mirroring `IntakeService`, but with a *different* allowed-field set.

### 2.1. Helper converters

Same idea as in the intake mapper: safe number/bool parsing.

**File:** `app/services/backlog_service.py`

```python
# app/services/backlog_service.py

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.sheets.backlog_reader import BacklogRow

import logging

logger = logging.getLogger(__name__)


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
    """
    Parse a comma-separated list of initiative_keys into a clean list.
    e.g. "INIT-001, INIT-002" -> ["INIT-001", "INIT-002"]
    """
    if not value:
        return []
    s = str(value)
    parts = [part.strip() for part in s.split(",") if part.strip()]
    return parts
```

---

### 2.2. Product-owned editable fields from central backlog

We now decide which fields Product can edit via the central backlog sheet.

These are **not** intake-owned fields; they are Product’s “control knobs”.

```python
# Fields that central product team can update from the central backlog sheet.
CENTRAL_EDITABLE_FIELDS = {
    # High-level info Product may refine
    "title",
    "requesting_team",
    "country",
    "product_area",

    # Strategic alignment
    "strategic_theme",
    "customer_segment",
    "initiative_type",
    "linked_objectives",
    "strategic_priority_coefficient",

    # Impact & effort (Product may override/refine intake estimates centrally)
    "expected_impact_description",
    "impact_metric",
    "impact_unit",
    "impact_low",
    "impact_expected",
    "impact_high",
    "effort_tshirt_size",
    "effort_engineering_days",
    "effort_other_teams_days",
    "infra_cost_estimate",
    "total_cost_estimate",  # optional if you let Product override derived totals

    # Dependencies / risk
    "dependencies_initiatives",  # structured list of initiative_keys
    "dependencies_others",
    "is_mandatory",
    "risk_level",
    "risk_description",
    "time_sensitivity",
    "deadline_date",

    # Lifecycle
    "status",

    # Scoring & frameworks
    "active_scoring_framework",
    "use_math_model",
    "value_score",
    "effort_score",
    "overall_score",
    "score_approved_by_user",

    # LLM notes / annotations Product may edit or extend
    "llm_notes",
}
```

> 🧠 Note:
>
> * We intentionally **don’t** include `llm_summary` or `score_llm_suggested`: those are backend/LLM-owned.
> * You *could* let Product edit `status` freely from central backlog, unlike intake where we restricted it.

---

### 2.3. Mapping a BacklogRow → “update dict” for Initiative

We now build a function that:

* Takes a `BacklogRow` dict (sheet columns),
* Produces a dict of `field_name → value` in `Initiative` terms.

```python
def backlog_row_to_update_data(row: BacklogRow) -> Dict[str, Any]:
    """
    Map central backlog sheet columns to Initiative fields.

    We assume the header names used in CENTRAL_BACKLOG_HEADER:
    - Initiative Key
    - Title
    - Requesting Team
    - Requester Name
    - Requester Email
    - Country
    - Product Area
    - Status
    - Strategic Theme
    - Customer Segment
    - Initiative Type
    - Hypothesis
    - Value Score
    - Effort Score
    - Overall Score
    - Active Scoring Framework
    - Use Math Model
    - Dependencies Initiatives
    - Dependencies Others
    - LLM Summary
    - LLM Notes
    - Strategic Priority Coefficient
    """

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

    # Linked objectives: you might store JSON string or comma-separated
    data["linked_objectives"] = row.get("Linked Objectives") or None  # column optional for now

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

    # LLM notes (summary is backend-owned, but notes can be human-augmented)
    data["llm_notes"] = row.get("LLM Notes") or None

    # Strategic priority coefficient
    data["strategic_priority_coefficient"] = _to_float(row.get("Strategic Priority Coefficient"))

    # You can add more mappings here if you add columns to the central backlog
    return data
```

> 🧩 This mapping is the central “schema contract” between the central backlog sheet and the Initiative model. You can grow it as the sheet grows.

---

### 2.4. The BacklogService class

Now the service that:

* Reads `initiative_key` from a row,
* Loads that `Initiative`,
* Applies only `CENTRAL_EDITABLE_FIELDS`.

```python
class BacklogService:
    """
    Service that updates Initiatives based on edits in the central backlog sheet.

    It is the "Product-owned" mirror of IntakeService:
    - IntakeService: department → Initiative (intake-owned fields).
    - BacklogService: central sheet → Initiative (product-owned fields).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def update_from_backlog_row(self, row: BacklogRow) -> Optional[Initiative]:
        """
        Apply changes from a central backlog row to the corresponding Initiative.

        Returns the updated Initiative, or None if the key was missing or not found.
        """
        initiative_key = self._extract_initiative_key(row)
        if not initiative_key:
            logger.warning("backlog.update.skip_no_key", extra={"row": row})
            return None

        initiative = (
            self.db.query(Initiative)
            .filter(Initiative.initiative_key == initiative_key)
            .one_or_none()
        )
        if initiative is None:
            logger.warning("backlog.update.missing_initiative", extra={"initiative_key": initiative_key})
            return None

        update_data = backlog_row_to_update_data(row)
        self._apply_central_update(initiative, update_data)

        self.db.commit()
        self.db.refresh(initiative)
        return initiative

    def _extract_initiative_key(self, row: BacklogRow) -> str:
        for candidate in ("Initiative Key", "initiative_key", "INITIATIVE_KEY"):
            if candidate in row and row[candidate]:
                return str(row[candidate]).strip()
        return ""

    def _apply_central_update(self, initiative: Initiative, data: Dict[str, Any]) -> None:
        """
        Apply product-owned updates to the Initiative, based on CENTRAL_EDITABLE_FIELDS.
        """
        for field_name, value in data.items():
            if field_name not in CENTRAL_EDITABLE_FIELDS:
                continue

            # You might add field-specific constraints here; e.g., restrict which statuses are allowed.
            setattr(initiative, field_name, value)
```

---

### 2.5. A job that uses BacklogReader + BacklogService

Example:

```python
# app/jobs/backlog_update_job.py

from app.db.session import SessionLocal
from app.sheets.client import SheetsClient
from app.sheets.backlog_reader import BacklogReader
from app.services.backlog_service import BacklogService

def run_backlog_update(
    backlog_spreadsheet_id: str,
    backlog_tab_name: str,
    sheets_service,
) -> None:
    db = SessionLocal()
    try:
        client = SheetsClient(sheets_service)
        reader = BacklogReader(client)
        service = BacklogService(db)

        rows = reader.get_rows(
            spreadsheet_id=backlog_spreadsheet_id,
            tab_name=backlog_tab_name,
        )

        for row_number, row_dict in rows:
            # Optionally look at row_number if you want to log it
            service.update_from_backlog_row(row_dict)
    finally:
        db.close()
```

Now you have full **two-way sync**:

* **Intake side:**

  * Intake sheets/tabs → `IntakeReader` → `IntakeService` → DB.
* **Central product side:**

  * Central backlog sheet → `BacklogReader` → `BacklogService` → DB.
* **Backlog writer:**

  * DB → `write_backlog_from_db` → central backlog sheet.

Product owns (and can override) things like:

* `dependencies_initiatives`
* `linked_objectives`
* `active_scoring_framework`
* `strategic_priority_coefficient`
* `use_math_model`
* `value_score`, `effort_score`, `overall_score`
* `status` (full state machine)

Departments own their intake fields.
Backend/LLM own derived fields like `llm_summary` and `score_llm_suggested`.

---

