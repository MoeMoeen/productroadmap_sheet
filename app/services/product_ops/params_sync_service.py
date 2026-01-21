# productroadmap_sheet_project/app/services/params_sync_service.py

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeParam
from app.sheets.client import SheetsClient
from app.sheets.params_reader import ParamsReader, ParamRowPair
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


class ParamsSyncService:
    """Sheet → DB sync for Initiative Parameters (Step 4)."""

    def __init__(self, client: SheetsClient) -> None:
        self.client = client
        self.reader = ParamsReader(client)

    def preview_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        max_rows: Optional[int] = None,
    ) -> List[ParamRowPair]:
        return self.reader.get_rows_for_sheet(
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
            max_rows=max_rows,
        )

    def sync_sheet_to_db(
        self,
        db: Session,
        spreadsheet_id: str,
        tab_name: str,
        commit_every: int = 200,
        initiative_keys: Optional[List[str]] = None,
    ) -> dict:
        """Upsert InitiativeParam per initiative_key + framework + param_name.

        Mapping:
        - initiative_key resolves Initiative
        - unique per (initiative_key, framework, param_name)
        - fields: framework, param_name, param_display, description, unit, value,
              source, approved, is_auto_seeded, min, max, notes

        Args:
            initiative_keys: Optional list of initiative_keys to filter rows. If provided, only rows
                            with matching initiative_keys are synced. If None, all rows are synced.

        Returns summary dict:
        {
            "row_count": int,
            "upserts": int,
            "created_params": int,
            "skipped_no_initiative": int,
            "skipped_no_name": int,
        }
        """
        rows = self.reader.get_rows_for_sheet(spreadsheet_id, tab_name)
        
        # Filter to selected initiative_keys if provided
        if initiative_keys is not None:
            allowed_keys = set(initiative_keys)
            rows = [(row_num, pr) for row_num, pr in rows if pr.initiative_key in allowed_keys]
        upserts = 0
        created = 0
        skipped_no_initiative = 0
        skipped_no_name = 0

        batch_count = 0
        for row_number, pr in rows:
            # Resolve Initiative
            initiative: Initiative | None = (
                db.query(Initiative)
                .filter(Initiative.initiative_key == pr.initiative_key)
                .one_or_none()
            )
            if not initiative:
                skipped_no_initiative += 1
                logger.debug(
                    "params.sync.skip_no_initiative",
                    extra={"row": row_number, "initiative_key": pr.initiative_key},
                )
                continue

            if not pr.param_name:
                skipped_no_name += 1
                logger.debug(
                    "params.sync.skip_no_name",
                    extra={"row": row_number, "initiative_key": pr.initiative_key},
                )
                continue

            # Find existing
            param = (
                db.query(InitiativeParam)
                .filter(
                    InitiativeParam.initiative_id == initiative.id,
                    InitiativeParam.framework == pr.framework,
                    InitiativeParam.param_name == pr.param_name,
                )
                .one_or_none()
            )

            created_now = False
            if not param:
                param = InitiativeParam(
                    initiative_id=initiative.id,
                    framework=pr.framework or "MATH_MODEL",
                    param_name=pr.param_name,
                )
                db.add(param)
                created_now = True

            # Map fields
            setattr(param, "framework", pr.framework or getattr(param, "framework", None))
            setattr(
                param,
                "param_display",
                getattr(pr, "param_display", None) if hasattr(pr, "param_display") else getattr(pr, "display", None),
            )
            setattr(param, "description", pr.description)
            setattr(param, "unit", pr.unit)
            value_out = pr.value
            if isinstance(value_out, str):
                try:
                    value_out = float(value_out)
                except ValueError:
                    value_out = None
            setattr(param, "value", value_out)
            setattr(param, "source", pr.source)
            # Optional fields via getattr to satisfy static checks
            pr_min = getattr(pr, "min", None)
            pr_max = getattr(pr, "max", None)
            pr_notes = getattr(pr, "notes", None)
            if pr_min is not None:
                setattr(param, "min", pr_min)
            if pr_max is not None:
                setattr(param, "max", pr_max)
            if pr_notes is not None:
                setattr(param, "notes", pr_notes)
            if pr.approved is not None:
                setattr(param, "approved", bool(pr.approved))
            if pr.is_auto_seeded is not None:
                setattr(param, "is_auto_seeded", bool(pr.is_auto_seeded))

            setattr(initiative, "updated_source", token(Provenance.FLOW4_SYNC_PARAMS))

            upserts += 1
            created += 1 if created_now else 0
            batch_count += 1
            if batch_count >= commit_every:
                db.commit()
                batch_count = 0

        if batch_count:
            db.commit()

        return {
            "row_count": len(rows),
            "upserts": upserts,
            "created_params": created,
            "skipped_no_initiative": skipped_no_initiative,
            "skipped_no_name": skipped_no_name,
        }
