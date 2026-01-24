# productroadmap_sheet_project/app/services/math_model_service.py

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel
from app.sheets.client import SheetsClient
from app.sheets.math_models_reader import MathModelsReader, MathModelRowPair
from app.services.product_ops.metric_chain_parser import parse_metric_chain
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
        - Map fields: formula_text (required to create), assumptions_text,
                  suggested_by_llm, approved_by_user, model_name, model_description_free_text,
                  metric_chain_text
        - Persist immediate_kpi_key and metric_chain_text (stored on initiative.metric_chain_json) for downstream scoring
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

            # Determine composite key: use target_kpi_key as identifier (or model_name if target_kpi not present)
            model_identifier = getattr(mm, "target_kpi_key", None) or getattr(mm, "model_name", None) or "default"
            
            # Find existing model by initiative_id + identifier
            math_model: InitiativeMathModel | None = None
            for existing_model in initiative.math_models:
                existing_key = getattr(existing_model, "target_kpi_key", None) or getattr(existing_model, "model_name", None) or "default"
                if existing_key == model_identifier:
                    math_model = existing_model
                    break
            
            created_now = False
            if not math_model:
                math_model = InitiativeMathModel()
                math_model.initiative_id = initiative.id
                db.add(math_model)
                initiative.math_models.append(math_model)
                created_now = True

            # Map fields
            setattr(math_model, "framework", getattr(math_model, "framework", None) or "MATH_MODEL")
            setattr(math_model, "formula_text", mm.formula_text or getattr(math_model, "formula_text", None))
            if getattr(mm, "model_name", None):
                setattr(math_model, "model_name", mm.model_name)
            if getattr(mm, "model_description_free_text", None):
                setattr(math_model, "model_description_free_text", mm.model_description_free_text)

            setattr(math_model, "assumptions_text", mm.assumptions_text)
            if mm.suggested_by_llm is not None:
                setattr(math_model, "suggested_by_llm", bool(mm.suggested_by_llm))
            if mm.approved_by_user is not None:
                setattr(math_model, "approved_by_user", bool(mm.approved_by_user))

            # Persist target_kpi_key and is_primary on math model
            target_kpi = getattr(mm, "target_kpi_key", None)
            if target_kpi:
                setattr(math_model, "target_kpi_key", target_kpi)
            is_primary = getattr(mm, "is_primary", None)
            if is_primary is not None:
                setattr(math_model, "is_primary", bool(is_primary))
            computed = getattr(mm, "computed_score", None)
            if computed is not None:
                setattr(math_model, "computed_score", float(computed))

            # Persist immediate_kpi_key on Initiative (for backwards compatibility)
            if getattr(mm, "immediate_kpi_key", None):
                setattr(initiative, "immediate_kpi_key", mm.immediate_kpi_key)

            # Parse and persist metric chain on math model (not initiative)
            if getattr(mm, "metric_chain_text", None):
                # Save raw text
                setattr(math_model, "metric_chain_text", mm.metric_chain_text)
                # Parse to JSON using metric_chain_parser
                try:
                    parsed_chain = parse_metric_chain(mm.metric_chain_text)
                    setattr(math_model, "metric_chain_json", parsed_chain)
                except Exception as e:
                    logger.warning(
                        "math_model.sync.metric_chain_parse_failed",
                        extra={
                            "initiative_key": mm.initiative_key,
                            "metric_chain_text": mm.metric_chain_text,
                            "error": str(e),
                        },
                    )
                    # Store as raw text in JSON for data preservation
                    setattr(math_model, "metric_chain_json", {"raw": mm.metric_chain_text, "parse_error": str(e)})

            # Save LLM notes on initiative if provided
            if getattr(mm, "llm_notes", None):
                setattr(initiative, "llm_notes", mm.llm_notes)

            # Update provenance
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
