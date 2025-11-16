"""IntakeService implementation (Flow 1 - Step 2).

Enhancements:
- Batch upsert with periodic commits (no hardcoded sizes).
- Initiative key write-back using a concrete Sheets writer.
- Status transition guard with optional override.
- Structured logging.
- Concurrency handling with IntegrityError retry (no hardcoded attempts).
"""
from __future__ import annotations

from typing import Any, Optional, Protocol
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.initiative import Initiative  # type: ignore
from app.schemas.initiative import InitiativeCreate  # type: ignore
from app.services.initiative_key import generate_initiative_key  # type: ignore
from app.services.intake_mapper import map_sheet_row_to_initiative_create  # type: ignore
from app.sheets.intake_reader import IntakeRow  # type: ignore

logger = logging.getLogger(__name__)

# Fields that are allowed to be written/updated from department intake sheets.
INTAKE_EDITABLE_FIELDS = {
    "title",
    "requesting_team",
    "requester_name",
    "requester_email",
    "country",
    "product_area",
    "problem_statement",
    "current_pain",
    "desired_outcome",
    "target_metrics",
    "hypothesis",
    "strategic_theme",
    "customer_segment",
    "initiative_type",
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
    "dependencies_others",
    "is_mandatory",
    "risk_level",
    "risk_description",
    "time_sensitivity",
    "deadline_date",
    "status",
}

# Allowed statuses configured via settings
ALLOWED_INTAKE_STATUSES = set(settings.INTAKE_ALLOWED_STATUSES)


class InitiativeKeyWriter(Protocol):
    def write_initiative_key(
        self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str
    ) -> None: ...


class IntakeService:
    def __init__(self, db: Session, key_writer: Optional[InitiativeKeyWriter] = None) -> None:
        self.db = db
        self.key_writer = key_writer

    def upsert_from_intake_row(
        self,
        row: IntakeRow,
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
        allow_status_override: bool = False,
    ) -> Initiative:
        dto: InitiativeCreate = map_sheet_row_to_initiative_create(row)
        if not dto.title:
            raise ValueError("Intake row missing required Title field")

        initiative = self._find_existing_initiative(
            row=row,
            source_sheet_id=source_sheet_id,
            source_tab_name=source_tab_name,
            source_row_number=source_row_number,
        )

        if initiative is None:
            initiative = self._create_from_intake(
                dto=dto,
                source_sheet_id=source_sheet_id,
                source_tab_name=source_tab_name,
                source_row_number=source_row_number,
            )
            logger.info(
                "intake.create",
                extra={
                    "initiative_key": getattr(initiative, "initiative_key", None),
                    "sheet_id": source_sheet_id,
                    "tab": source_tab_name,
                    "row": source_row_number,
                },
            )
            key_val = getattr(initiative, "initiative_key", None)
            if key_val:
                self._backfill_initiative_key(source_sheet_id, source_tab_name, source_row_number, str(key_val))
        else:
            self._apply_intake_update(initiative, dto, allow_status_override=allow_status_override)
            logger.debug(
                "intake.update",
                extra={
                    "initiative_key": getattr(initiative, "initiative_key", None),
                    "sheet_id": source_sheet_id,
                    "tab": source_tab_name,
                    "row": source_row_number,
                },
            )

        self.db.commit()
        self.db.refresh(initiative)
        return initiative

    def upsert_many(
        self,
        rows: list[IntakeRow],
        source_sheet_id: str,
        source_tab_name: str,
        start_row_number: int,
        commit_every: Optional[int] = None,
        allow_status_override: bool = False,
    ) -> list[Initiative]:
        commit_every = commit_every or settings.INTAKE_BATCH_COMMIT_EVERY
        out: list[Initiative] = []
        for idx, row in enumerate(rows):
            row_num = start_row_number + idx
            initiative = self.upsert_from_intake_row(
                row=row,
                source_sheet_id=source_sheet_id,
                source_tab_name=source_tab_name,
                source_row_number=row_num,
                allow_status_override=allow_status_override,
            )
            out.append(initiative)

            if commit_every and (idx + 1) % commit_every == 0:
                try:
                    self.db.commit()
                    logger.info(
                        "intake.batch_commit",
                        extra={"count": idx + 1, "sheet_id": source_sheet_id, "tab": source_tab_name},
                    )
                except Exception:
                    self.db.rollback()
                    logger.exception("intake.batch_commit_failed")
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("intake.final_commit_failed")
        return out

    def _find_existing_initiative(
        self,
        row: IntakeRow,
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
    ) -> Optional[Initiative]:
        initiative_key = self._extract_initiative_key(row)
        if initiative_key:
            existing = (
                self.db.query(Initiative).filter(Initiative.initiative_key == initiative_key).one_or_none()
            )
            if existing is not None:
                return existing

        return (
            self.db.query(Initiative)
            .filter(
                Initiative.source_sheet_id == source_sheet_id,
                Initiative.source_tab_name == source_tab_name,
                Initiative.source_row_number == source_row_number,
            )
            .one_or_none()
        )

    @staticmethod
    def _extract_initiative_key(row: IntakeRow) -> Optional[str]:
        for key in ("initiative_key", "Initiative Key", "INITIATIVE_KEY"):
            if key in row and row[key]:
                return str(row[key]).strip()
        return None

    def _create_from_intake(
        self,
        dto: InitiativeCreate,
        source_sheet_id: str,
        source_tab_name: str,
        source_row_number: int,
    ) -> Initiative:
        attempts = 0
        last_error: Optional[Exception] = None
        max_attempts = max(1, int(settings.INTAKE_CREATE_MAX_RETRIES))
        while attempts < max_attempts:
            attempts += 1
            initiative_key = generate_initiative_key(self.db)
            initiative = Initiative(
                initiative_key=initiative_key,
                source_sheet_id=source_sheet_id,
                source_tab_name=source_tab_name,
                source_row_number=source_row_number,
                **dto.model_dump(),
            )
            self.db.add(initiative)
            try:
                self.db.flush()
                return initiative
            except IntegrityError as exc:
                self.db.rollback()
                last_error = exc
                logger.warning("intake.key_conflict_retry", extra={"attempt": attempts})
        if last_error:
            raise last_error
        return initiative  # defensive

    def _apply_intake_update(
        self, initiative: Initiative, dto: InitiativeCreate, allow_status_override: bool = False
    ) -> None:
        data = dto.model_dump(exclude_unset=True)
        for field_name, value in data.items():
            if field_name not in INTAKE_EDITABLE_FIELDS:
                continue
            if field_name == "status":
                if str(value).strip().lower() not in {s.lower() for s in ALLOWED_INTAKE_STATUSES}:
                    continue
                current = (initiative.status or "").strip().lower()
                new = (str(value) or "").strip().lower()
                if not allow_status_override and current == "withdrawn" and new == "new":
                    logger.info(
                        "intake.status_blocked",
                        extra={
                            "initiative_key": initiative.initiative_key,
                            "from": current,
                            "to": new,
                        },
                    )
                    continue
            setattr(initiative, field_name, value)

    def _backfill_initiative_key(
        self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str
    ) -> None:
        if not self.key_writer:
            return
        try:
            self.key_writer.write_initiative_key(sheet_id, tab_name, row_number, initiative_key)
        except Exception:
            logger.exception("intake.key_backfill_failed")


__all__ = [
    "IntakeService",
    "INTAKE_EDITABLE_FIELDS",
    "ALLOWED_INTAKE_STATUSES",
    "InitiativeKeyWriter",
]
