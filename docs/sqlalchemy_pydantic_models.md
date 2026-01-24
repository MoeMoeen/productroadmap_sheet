We’ll cover:

1. `Initiative` – SQLAlchemy + Pydantic
2. `Roadmap` – SQLAlchemy + Pydantic
3. `RoadmapEntry` – SQLAlchemy + Pydantic
4. Tiny scoring stubs so we don’t paint ourselves into a corner

---

## 1. SQLAlchemy base + session (for context)

If you don’t already have this, you’ll want something like:

**`app/db/base.py`**

```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

**`app/db/session.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings  # wherever you keep DB URL

engine = create_engine(settings.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

I’ll assume these exist and just import `Base` in models.

---

## 2. SQLAlchemy model: `Initiative`

**File:** `app/db/models/initiative.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Initiative(Base):
    __tablename__ = "initiatives"

    id = Column(Integer, primary_key=True, index=True)

    # A. Identity & source
    initiative_key = Column(String(50), unique=True, index=True, nullable=False)
    source_sheet_id = Column(String(255), nullable=True)
    source_tab_name = Column(String(255), nullable=True)
    source_row_number = Column(Integer, nullable=True)

    # B. Ownership & requester
    title = Column(String(255), nullable=False)
    requesting_team = Column(String(100), nullable=True)
    requester_name = Column(String(255), nullable=True)
    requester_email = Column(String(255), nullable=True)
    country = Column(String(50), nullable=True)
    product_area = Column(String(100), nullable=True)

    # C. Problem & context
    problem_statement = Column(Text, nullable=True)
    current_pain = Column(Text, nullable=True)
    desired_outcome = Column(Text, nullable=True)
    target_metrics = Column(Text, nullable=True)
    hypothesis = Column(Text, nullable=True)
    llm_summary = Column(Text, nullable=True)

    # D. Strategic alignment & classification
    strategic_theme = Column(String(100), nullable=True)
    customer_segment = Column(String(100), nullable=True)
    initiative_type = Column(String(100), nullable=True)
    strategic_priority_coefficient = Column(Float, nullable=False, default=1.0)
    linked_objectives = Column(JSON, nullable=True)  # list of IDs/names, later → proper relation

    # E. Impact & value modeling (high-level)
    expected_impact_description = Column(Text, nullable=True)
    impact_metric = Column(String(100), nullable=True)
    impact_unit = Column(String(20), nullable=True)
    impact_low = Column(Float, nullable=True)
    impact_expected = Column(Float, nullable=True)
    impact_high = Column(Float, nullable=True)

    # F. Effort & cost (high-level)
    effort_tshirt_size = Column(String(10), nullable=True)  # XS/S/M/L/XL
    effort_engineering_days = Column(Float, nullable=True)
    effort_other_teams_days = Column(Float, nullable=True)
    infra_cost_estimate = Column(Float, nullable=True)
    total_cost_estimate = Column(Float, nullable=True)

    # G. Risk, dependencies, constraints
    dependencies_others = Column(Text, nullable=True)
    is_mandatory = Column(Boolean, nullable=False, default=False)
    risk_level = Column(String(50), nullable=True)
    risk_description = Column(Text, nullable=True)
    time_sensitivity = Column(String(50), nullable=True)
    deadline_date = Column(Date, nullable=True)

    # H. Lifecycle & workflow
    status = Column(String(50), nullable=False, default="new")
    missing_fields = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_user_id = Column(String(100), nullable=True)

    # I. Scoring summary (framework-agnostic)
    active_scoring_framework = Column(String(50), nullable=True)
    value_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    score_llm_suggested = Column(Boolean, nullable=False, default=False)
    score_approved_by_user = Column(Boolean, nullable=False, default=False)

    # J. LLM & math-model hooks
    use_math_model = Column(Boolean, nullable=False, default=False)
    llm_notes = Column(Text, nullable=True)

    # Relationships
    math_models = relationship("InitiativeMathModel", back_populates="initiative", cascade="all, delete-orphan")
    roadmap_entries = relationship("RoadmapEntry", back_populates="initiative")
    # optional: scoring history
    scores = relationship("InitiativeScore", back_populates="initiative")
```

---

## 3. SQLAlchemy models: `Roadmap` & `RoadmapEntry`

**File:** `app/db/models/roadmap.py`

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # e.g. "2025 H1", "Growth Focus", "Regulatory Roadmap"
    timeframe_label = Column(String(100), nullable=True)
    owner_team = Column(String(100), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Many-to-many via RoadmapEntry
    entries = relationship("RoadmapEntry", back_populates="roadmap", cascade="all, delete-orphan")
```

**File:** `app/db/models/roadmap_entry.py`

```python
from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Boolean,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class RoadmapEntry(Base):
    """
    Link between Roadmap and Initiative, with metadata per roadmap.
    """

    __tablename__ = "roadmap_entries"

    id = Column(Integer, primary_key=True, index=True)

    roadmap_id = Column(Integer, ForeignKey("roadmaps.id"), nullable=False, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)

    # Priority and scheduling info for this roadmap
    priority_rank = Column(Integer, nullable=True)  # 1 = highest priority
    planned_quarter = Column(String(20), nullable=True)  # e.g. "2025-Q1"
    planned_year = Column(Integer, nullable=True)

    # Flags for optimization decisions
    is_selected = Column(Boolean, nullable=False, default=False)
    is_locked_in = Column(Boolean, nullable=False, default=False)  # manually locked by product
    is_mandatory_in_this_roadmap = Column(Boolean, nullable=False, default=False)

    # Scores as used in THIS roadmap (can differ from global initiative scores if we want)
    value_score_used = Column(Float, nullable=True)
    effort_score_used = Column(Float, nullable=True)
    overall_score_used = Column(Float, nullable=True)

    # Optional: which optimization run / scenario created this entry
    optimization_run_id = Column(String(100), nullable=True)
    scenario_label = Column(String(100), nullable=True)

    roadmap = relationship("Roadmap", back_populates="entries")
    initiative = relationship("Initiative", back_populates="roadmap_entries")
```

---

## 4. SQLAlchemy scoring stubs: `InitiativeMathModel` & `InitiativeScore`

Just minimal for now so the relationships compile.

**File:** `app/db/models/scoring.py`

```python
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class InitiativeMathModel(Base):
    """
    Stores the full mathematical model for an initiative:
    - formula_text: how value is computed
    - parameters_json: parameter names, types, ranges, etc.
    - assumptions_text: human-readable assumptions
    """

    __tablename__ = "initiative_math_models"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), unique=True, nullable=False)

    formula_text = Column(Text, nullable=False)
    parameters_json = Column(JSON, nullable=True)  # e.g. {"traffic": {...}, "uplift": {...}}
    assumptions_text = Column(Text, nullable=True)

    suggested_by_llm = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    initiative = relationship("Initiative", back_populates="math_model")


class InitiativeScore(Base):
    """
    Optional scoring history table:
    keeps track of scores per framework / per run.
    """

    __tablename__ = "initiative_scores"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False, index=True)

    framework_name = Column(String(50), nullable=False)  # e.g. "RICE", "MATH_MODEL", "CUSTOM_X"
    value_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)

    inputs_json = Column(JSON, nullable=True)  # raw inputs like RICE fields, parameters, etc.
    llm_suggested = Column(Boolean, nullable=False, default=False)
    approved_by_user = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="scores")
```

---

## 5. Pydantic schemas – `Initiative`

We’ll define **read**, **create**, and **update** schemas. You can add specialized ones later (e.g. `InitiativeCreateFromSheet` vs API).

**File:** `app/schemas/initiative.py`

> I’ll assume Pydantic v2; if you’re on v1, just swap `model_config` → `Config` and `from_attributes = True` → `orm_mode = True`.

```python
from datetime import date, datetime
from typing import List, Optional, Any

from pydantic import BaseModel, Field


# ---- Base shared fields ----

class InitiativeBase(BaseModel):
    title: str = Field(..., min_length=3)

    requesting_team: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    country: Optional[str] = None
    product_area: Optional[str] = None

    problem_statement: Optional[str] = None
    current_pain: Optional[str] = None
    desired_outcome: Optional[str] = None
    target_metrics: Optional[str] = None
    hypothesis: Optional[str] = None

    strategic_theme: Optional[str] = None
    customer_segment: Optional[str] = None
    initiative_type: Optional[str] = None
    strategic_priority_coefficient: float = 1.0
    linked_objectives: Optional[Any] = None  # list/dict, we can tighten later

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None
    impact_low: Optional[float] = None
    impact_expected: Optional[float] = None
    impact_high: Optional[float] = None

    effort_tshirt_size: Optional[str] = None
    effort_engineering_days: Optional[float] = None
    effort_other_teams_days: Optional[float] = None
    infra_cost_estimate: Optional[float] = None
    total_cost_estimate: Optional[float] = None

    dependencies_others: Optional[str] = None
    is_mandatory: bool = False
    risk_level: Optional[str] = None
    risk_description: Optional[str] = None
    time_sensitivity: Optional[str] = None
    deadline_date: Optional[date] = None

    status: str = "new"
    active_scoring_framework: Optional[str] = None

    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None
    score_llm_suggested: bool = False
    score_approved_by_user: bool = False

    use_math_model: bool = False
    llm_notes: Optional[str] = None


# ---- Create / update variants ----

class InitiativeCreate(InitiativeBase):
    """
    For creating initiatives via API or from Sheets after validation.
    initiative_key and source_* are generated by backend.
    """
    pass


class InitiativeUpdate(BaseModel):
    """
    All fields optional for partial updates (PATCH semantics).
    """
    title: Optional[str] = None

    requesting_team: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    country: Optional[str] = None
    product_area: Optional[str] = None

    problem_statement: Optional[str] = None
    current_pain: Optional[str] = None
    desired_outcome: Optional[str] = None
    target_metrics: Optional[str] = None
    hypothesis: Optional[str] = None

    strategic_theme: Optional[str] = None
    customer_segment: Optional[str] = None
    initiative_type: Optional[str] = None
    strategic_priority_coefficient: Optional[float] = None
    linked_objectives: Optional[Any] = None

    expected_impact_description: Optional[str] = None
    impact_metric: Optional[str] = None
    impact_unit: Optional[str] = None
    impact_low: Optional[float] = None
    impact_expected: Optional[float] = None
    impact_high: Optional[float] = None

    effort_tshirt_size: Optional[str] = None
    effort_engineering_days: Optional[float] = None
    effort_other_teams_days: Optional[float] = None
    infra_cost_estimate: Optional[float] = None
    total_cost_estimate: Optional[float] = None

    dependencies_others: Optional[str] = None
    is_mandatory: Optional[bool] = None
    risk_level: Optional[str] = None
    risk_description: Optional[str] = None
    time_sensitivity: Optional[str] = None
    deadline_date: Optional[date] = None

    status: Optional[str] = None
    active_scoring_framework: Optional[str] = None

    value_score: Optional[float] = None
    effort_score: Optional[float] = None
    overall_score: Optional[float] = None
    score_llm_suggested: Optional[bool] = None
    score_approved_by_user: Optional[bool] = None

    use_math_model: Optional[bool] = None
    llm_notes: Optional[str] = None


class InitiativeRead(InitiativeBase):
    """
    For responses: includes IDs and derived fields.
    """
    id: int
    initiative_key: str
    source_sheet_id: Optional[str] = None
    source_tab_name: Optional[str] = None
    source_row_number: Optional[int] = None

    llm_summary: Optional[str] = None
    missing_fields: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[str] = None

    model_config = {
        "from_attributes": True  # Pydantic v2; for v1 use `Config.orm_mode = True`
    }
```

You might later add a dedicated `InitiativeFromSheet` schema that matches sheet columns exactly, but this is a good generic start.

---

## 6. Pydantic schemas – `Roadmap` & `RoadmapEntry`

**File:** `app/schemas/roadmap.py`

```python
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class RoadmapBase(BaseModel):
    name: str
    description: Optional[str] = None
    timeframe_label: Optional[str] = None
    owner_team: Optional[str] = None


class RoadmapCreate(RoadmapBase):
    pass


class RoadmapRead(RoadmapBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

**File:** `app/schemas/roadmap_entry.py`

```python
from typing import Optional

from pydantic import BaseModel


class RoadmapEntryBase(BaseModel):
    roadmap_id: int
    initiative_id: int

    priority_rank: Optional[int] = None
    planned_quarter: Optional[str] = None
    planned_year: Optional[int] = None

    is_selected: bool = False
    is_locked_in: bool = False
    is_mandatory_in_this_roadmap: bool = False

    value_score_used: Optional[float] = None
    effort_score_used: Optional[float] = None
    overall_score_used: Optional[float] = None

    optimization_run_id: Optional[str] = None
    scenario_label: Optional[str] = None


class RoadmapEntryCreate(RoadmapEntryBase):
    pass


class RoadmapEntryRead(RoadmapEntryBase):
    id: int

    model_config = {"from_attributes": True}
```

---
