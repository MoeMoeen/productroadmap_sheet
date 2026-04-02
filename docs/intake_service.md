2. **Minimal `intake_service`**: row → `InitiativeCreate` → upsert

## 2. Minimal `intake_service`: row → InitiativeCreate → upsert

Goal: given:

* A **dict** representing a row from an **intake sheet** (columns → values),
* Some metadata (sheet id, tab name, row number),

we:

1. Map it to `InitiativeCreate`.
2. Generate/resolve `initiative_key`.
3. Upsert into DB.

### 2.1. A simple mapper: sheet row → InitiativeCreate

**File:** `app/services/intake_mapper.py`

(You can also keep this inside `intake_service.py`, but I’d separate for clarity.)

```python
from typing import Dict, Any

from app.schemas.initiative import InitiativeCreate


def map_sheet_row_to_initiative_create(row: Dict[str, Any]) -> InitiativeCreate:
    """
    Map a single Google Sheets row (column_name -> value)
    to an InitiativeCreate schema.

    Assumes the sheet header names match these keys.
    You can adjust the mapping dict if headers differ.
    """

    # Example header names on the intake sheet:
    # Title, Department, Requesting Team, Requester Name, Requester Email,
    # Country, Product Area, Problem Statement, Deadline Date, Lifecycle Status / Status

    return InitiativeCreate(
        title=row.get("Title", "").strip(),
        department=row.get("Department"),
        requesting_team=row.get("Requesting Team"),
        requester_name=row.get("Requester Name"),
        requester_email=row.get("Requester Email"),
        country=row.get("Country"),
        product_area=row.get("Product Area"),

        problem_statement=row.get("Problem Statement"),
        deadline_date=_to_date(row.get("Deadline Date")),

        lifecycle_status=(row.get("Lifecycle Status") or row.get("Status") or "new").strip() or "new",
    )


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"true", "yes", "y", "1", "✅"}
```

This mapper should stay limited to fields that are genuinely owned by the intake sheet.
Downstream planning, scoring, effort, dependency, and risk fields belong in Central Backlog,
Product Ops, MathModels, or Optimization flows rather than department intake.

---

### 2.2. Generating an initiative_key

For now, keep it simple: maybe `sheet_prefix-row_number`, or a running sequence.

**File:** `app/services/initiative_key.py`

```python
from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative


def generate_initiative_key(db: Session) -> str:
    """
    Very naive sequential key generator.
    Later you can replace with a sequence, prefix per year, etc.
    """
    last = db.query(Initiative).order_by(Initiative.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"INIT-{next_id:06d}"
```

You might later want something more sophisticated (per year, per org, etc.), but this works.

---

### 2.3. Upsert logic in `intake_service`

**File:** `app/services/intake_service.py`

```python
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.schemas.initiative import InitiativeCreate
from app.services.intake_mapper import map_sheet_row_to_initiative_create
from app.services.initiative_key import generate_initiative_key


class IntakeService:
    """
    Handles intake from department sheets into the canonical Initiative table.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync_row(
        self,
        row: Dict[str, Any],
        sheet_id: str,
        tab_name: str,
        row_number: int,
    ) -> Initiative:
        """
        Sync a single intake sheet row into the DB.

        Strategy:
        - If an initiative already exists with this (sheet_id, tab_name, row_number),
          update it.
        - Otherwise, create a new initiative with a new initiative_key.
        """

        # 1) Map row to validated InitiativeCreate schema
        data: InitiativeCreate = map_sheet_row_to_initiative_create(row)

        # 2) Try to find existing initiative by source metadata
        existing: Optional[Initiative] = (
            self.db.query(Initiative)
            .filter(
                Initiative.source_sheet_id == sheet_id,
                Initiative.source_tab_name == tab_name,
                Initiative.source_row_number == row_number,
            )
            .first()
        )

        if existing:
            initiative = self._update_existing_initiative(existing, data)
        else:
            initiative = self._create_new_initiative(data, sheet_id, tab_name, row_number)

        self.db.commit()
        self.db.refresh(initiative)
        return initiative

    def _create_new_initiative(
        self,
        data: InitiativeCreate,
        sheet_id: str,
        tab_name: str,
        row_number: int,
    ) -> Initiative:
        initiative_key = generate_initiative_key(self.db)

        initiative = Initiative(
            initiative_key=initiative_key,
            source_sheet_id=sheet_id,
            source_tab_name=tab_name,
            source_row_number=row_number,
            **data.model_dump(),
        )
        self.db.add(initiative)
        return initiative

    def _update_existing_initiative(
        self,
        initiative: Initiative,
        data: InitiativeCreate,
    ) -> Initiative:
        # Apply updates field-by-field; here we just do a naive overwrite for non-null fields
        update_dict = data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(initiative, field, value)
        self.db.add(initiative)
        return initiative
```

Usage example in a job:

```python
# app/jobs/sync_intake_job.py

from app.db.session import SessionLocal
from app.services.intake_service import IntakeService
from app.sheets.intake_reader import get_rows_for_sheet  # you’ll implement this

def run_sync_for_sheet(sheet_id: str, tab_name: str) -> None:
    db = SessionLocal()
    try:
        rows = get_rows_for_sheet(sheet_id, tab_name)  # yields (row_number, row_dict)
        service = IntakeService(db)
        for row_number, row in rows:
            service.sync_row(row, sheet_id, tab_name, row_number)
    finally:
        db.close()
```

---

That gives you:

* A **pluggable scoring system** (`ScoringFramework` interface, registry, scoring service).
* A **minimal but real intake pipeline**:

  * Intake sheet row → Pydantic validation → Initiative ORM → upsert.

If you want next, we can:

* Add **LLM hooks** into scoring (e.g. `scoring_assistant.py`), or
* Design an initial **optimization_service** that uses `value_score`/`effort_score` to build a portfolio LP.
