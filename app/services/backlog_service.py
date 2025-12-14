# productroadmap_sheet_project/app/services/backlog_service.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative  # type: ignore
from app.sheets.backlog_reader import BacklogRow  # type: ignore
from app.config import settings
from app.utils.header_utils import get_value_by_header_alias

from .backlog_mapper import backlog_row_to_update_data

logger = logging.getLogger(__name__)


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
    "total_cost_estimate",

    # Dependencies / risk
    "dependencies_initiatives",
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

class BacklogService:
    """
    Updates Initiatives in the database based on edits in the central backlog sheet.
    Product-owned mirror of IntakeService.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def update_from_backlog_row(self, row: BacklogRow) -> Optional[Initiative]:
        """Apply changes from a central backlog row to the corresponding Initiative."""
        initiative_key = self._extract_initiative_key(row)
        if not initiative_key:
            logger.info("backlog.update.skip_no_key")
            return None

        stmt = select(Initiative).where(Initiative.initiative_key == initiative_key)
        initiative = self.db.execute(stmt).scalar_one_or_none()
        if initiative is None:
            logger.info("backlog.update.missing_initiative", extra={"initiative_key": initiative_key})
            return None

        update_data = backlog_row_to_update_data(row)
        self._apply_central_update(initiative, update_data)

        # Stamp source of update
        try:
            setattr(initiative, "updated_source", "backlog")
        except Exception:
            logger.debug("backlog.updated_source_set_failed_on_update")

        self.db.commit()
        self.db.refresh(initiative)
        return initiative

    @staticmethod
    def _extract_initiative_key(row: BacklogRow) -> str:
        """Extract the initiative key from a backlog row dict."""
        val = get_value_by_header_alias(
            row,
            getattr(settings, "INTAKE_KEY_HEADER_NAME", "Initiative Key"),
            getattr(settings, "INTAKE_KEY_HEADER_ALIASES", []),
        )
        return (str(val).strip() if val else "")

    def update_many(
        self,
        rows: List[BacklogRow] | List[tuple[int, BacklogRow]],
        commit_every: Optional[int] = None,
    ) -> int:
        """Batch update many backlog rows with periodic commits.

        Returns the number of successfully updated initiatives.
        """
        batch = commit_every or getattr(settings, "INTAKE_BATCH_COMMIT_EVERY", 100)
        updated = 0
        for idx, item in enumerate(rows):
            row: BacklogRow
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
                # (row_number, row_dict)
                row = item[1]
            else:
                row = item  # type: ignore[assignment]

            initiative_key = self._extract_initiative_key(row)
            if not initiative_key:
                continue

            stmt = select(Initiative).where(Initiative.initiative_key == initiative_key)
            initiative = self.db.execute(stmt).scalar_one_or_none()
            if initiative is None:
                continue

            update_data = backlog_row_to_update_data(row)
            self._apply_central_update(initiative, update_data)
            try:
                setattr(initiative, "updated_source", "backlog")
            except Exception:
                logger.debug("backlog.updated_source_set_failed_on_update_many")
            updated += 1

            if batch and (idx + 1) % batch == 0:
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    logger.exception("backlog.batch_commit_failed")

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("backlog.final_commit_failed")
        return updated

    @staticmethod
    def _apply_central_update(initiative: Initiative, data: Dict[str, Any]) -> None:
        """Apply central editable fields from data to the Initiative instance."""
        for field_name, value in data.items():
            if field_name not in CENTRAL_EDITABLE_FIELDS:
                continue
            setattr(initiative, field_name, value)


__all__ = [
    "BacklogService",
    "CENTRAL_EDITABLE_FIELDS",
    "backlog_row_to_update_data",
]
