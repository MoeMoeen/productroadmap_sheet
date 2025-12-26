# productroadmap_sheet_project/app/services/math_model_service.py

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel
from app.sheets.client import SheetsClient
from app.sheets.math_models_reader import MathModelsReader, MathModelRowPair
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


class MathModelSyncService:
    """Sheet ↔ DB sync for MathModels (Sheet → DB for Step 4)."""

    def __init__(self, client: SheetsClient) -> None:
        self.client = client
        self.reader = MathModelsReader(client)

    def preview_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        max_rows: Optional[int] = None,
    ) -> List[MathModelRowPair]:
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
        commit_every: int = 100,
        initiative_keys: Optional[List[str]] = None,
    ) -> dict:
        """Upsert InitiativeMathModel from Sheet → DB.

        Rules:
        - Resolve initiative by initiative_key
        - Upsert math model object; set initiative.math_model to this object
        - Map fields: formula_text (required to create), parameters_json, assumptions_text,
                      suggested_by_llm, approved_by_user
        - If row provides llm_notes, store on Initiative.llm_notes
        
        Args:
            initiative_keys: Optional list of initiative_keys to filter rows. If provided, only rows
                            with matching initiative_keys are synced. If None, all rows are synced.
        """
        rows = self.reader.get_rows_for_sheet(spreadsheet_id, tab_name)
        
        # Filter to selected initiative_keys if provided
        if initiative_keys is not None:
            allowed_keys = set(initiative_keys)
            rows = [(row_num, mm) for row_num, mm in rows if mm.initiative_key in allowed_keys]
        updated = 0
        skipped_no_initiative = 0
        skipped_no_formula = 0
        created_models = 0

        batch_count = 0
        for row_number, mm in rows:
            # Resolve initiative
            initiative: Initiative | None = (
                db.query(Initiative)
                .filter(Initiative.initiative_key == mm.initiative_key)
                .one_or_none()
            )
            if not initiative:
                skipped_no_initiative += 1
                logger.debug(
                    "math_model.sync.skip_no_initiative",
                    extra={"row": row_number, "initiative_key": mm.initiative_key},
                )
                continue

            # Ensure formula_text exists for creation
            if not mm.formula_text:
                skipped_no_formula += 1
                logger.debug(
                    "math_model.sync.skip_no_formula",
                    extra={"row": row_number, "initiative_key": mm.initiative_key},
                )
                continue

            # Get or create math model
            math_model: InitiativeMathModel | None = initiative.math_model
            created_now = False
            if not math_model:
                math_model = InitiativeMathModel()
                db.add(math_model)
                created_now = True

            # Map fields
            setattr(math_model, "framework", getattr(math_model, "framework", None) or "MATH_MODEL")
            setattr(math_model, "formula_text", mm.formula_text or getattr(math_model, "formula_text", None))

            # parameters_json: parse if string
            params_obj = None
            if isinstance(mm.parameters_json, dict):
                params_obj = mm.parameters_json
            elif isinstance(mm.parameters_json, str) and mm.parameters_json.strip():
                try:
                    params_obj = json.loads(mm.parameters_json)
                except Exception:
                    logger.warning(
                        "math_model.sync.bad_parameters_json",
                        extra={"row": row_number, "initiative_key": mm.initiative_key},
                    )
                    params_obj = None
            setattr(math_model, "parameters_json", params_obj)

            setattr(math_model, "assumptions_text", mm.assumptions_text)
            if mm.suggested_by_llm is not None:
                setattr(math_model, "suggested_by_llm", bool(mm.suggested_by_llm))
            if mm.approved_by_user is not None:
                setattr(math_model, "approved_by_user", bool(mm.approved_by_user))

            # Save LLM notes on initiative if provided
            if getattr(mm, "llm_notes", None):
                setattr(initiative, "llm_notes", mm.llm_notes)

            # Link initiative to model
            db.flush()  # assign id if new
            initiative.math_model = math_model
            setattr(initiative, "updated_source", token(Provenance.FLOW4_SYNC_MATHMODELS))

            updated += 1
            created_models += 1 if created_now else 0
            batch_count += 1
            if batch_count >= commit_every:
                db.commit()
                batch_count = 0

        if batch_count:
            db.commit()

        return {
            "row_count": len(rows),
            "updated": updated,
            "created_models": created_models,
            "skipped_no_initiative": skipped_no_initiative,
            "skipped_no_formula": skipped_no_formula,
        }
