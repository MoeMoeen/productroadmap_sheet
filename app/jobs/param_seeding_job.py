# productroadmap_sheet_project/app/jobs/param_seeding_job.py

"""Job to seed Params sheet from approved MathModels formulas.

Step 8: Read approved MathModels, extract identifiers, diff against Params,
call LLM for missing identifiers, and append new rows.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

from app.config import settings
from app.llm.client import LLMClient
from app.llm.scoring_assistant import suggest_param_metadata_for_model
from app.sheets.client import SheetsClient
from app.sheets.math_models_reader import MathModelsReader
from app.sheets.params_reader import ParamsReader
from app.sheets.params_writer import ParamsWriter
from app.utils.safe_eval import extract_identifiers, validate_formula

logger = logging.getLogger(__name__)


class ParamSeedingStats:
    """Statistics for param seeding job run."""

    def __init__(self) -> None:
        self.rows_scanned_mathmodelstab = 0
        self.eligible_rows_mathmodelstab = 0
        self.seeded_params_paramsstab = 0
        self.llm_calls = 0
        self.skipped_row_mathmodeltab_no_missing = 0
        self.skipped_row_mathmodeltab_unapproved = 0
        self.skipped_row_mathmodeltab_no_identifiers = 0
        self.skipped_row_mathmodeltab_invalid_formula = 0

    def summary(self) -> Dict[str, int]:
        return {
            "rows_scanned_mathmodelstab": self.rows_scanned_mathmodelstab,
            "eligible_rows_mathmodelstab": self.eligible_rows_mathmodelstab,
            "seeded_params_paramsstab": self.seeded_params_paramsstab,
            "llm_calls": self.llm_calls,
            "skipped_row_mathmodeltab_no_missing": self.skipped_row_mathmodeltab_no_missing,
            "skipped_row_mathmodeltab_unapproved": self.skipped_row_mathmodeltab_unapproved,
            "skipped_row_mathmodeltab_no_identifiers": self.skipped_row_mathmodeltab_no_identifiers,
            "skipped_row_mathmodeltab_invalid_formula": self.skipped_row_mathmodeltab_invalid_formula,
        }


def run_param_seeding_job(
    sheets_client: SheetsClient,
    spreadsheet_id: str,
    mathmodels_tab: str,
    params_tab: str,
    llm_client: LLMClient,
    max_llm_calls: int = 10,
    limit: int | None = None,
) -> ParamSeedingStats:
    """Seed Params sheet from approved MathModels.

    Workflow:
    1. Read all approved MathModels rows
    2. Extract identifiers from formula_text
    3. Build existing param keys from ParamsReader
    4. For each model with missing identifiers:
       - Call LLM to suggest param metadata
       - Append new params via ParamsWriter
    5. Return stats

    Args:
        spreadsheet_id: ProductOps spreadsheet ID
        mathmodels_tab: MathModels tab name
        params_tab: Params tab name
        llm_client: LLM client for metadata suggestions
        max_llm_calls: Max LLM calls to make
        limit: Optional limit on rows to scan

    Returns:
        ParamSeedingStats with counts
    """
    stats = ParamSeedingStats()

    math_reader = MathModelsReader(sheets_client)
    params_reader = ParamsReader(sheets_client)
    params_writer = ParamsWriter(sheets_client)

    # Read approved MathModels
    math_rows = math_reader.get_rows_for_sheet(
        spreadsheet_id=spreadsheet_id,
        tab_name=mathmodels_tab,
        max_rows=limit,
    )

    # Build existing param keys: (initiative_key, framework, param_name) set
    # This ensures we don't block future RICE/WSJF params with same name
    existing_params_rows = params_reader.get_rows_for_sheet(
        spreadsheet_id=spreadsheet_id,
        tab_name=params_tab,
    )
    existing_keys: Set[tuple[str, str, str]] = {
        (row.initiative_key, row.framework or "MATH_MODEL", row.param_name)
        for _, row in existing_params_rows
    }

    logger.info(f"Loaded {len(existing_keys)} existing params")

    # Process MathModels
    for row_number, math_row in math_rows:
        stats.rows_scanned_mathmodelstab += 1

        # Skip unapproved
        if not math_row.approved_by_user:
            logger.info(f"Skipping unapproved MathModel row {row_number} {math_row.initiative_key}")
            stats.skipped_row_mathmodeltab_unapproved += 1
            continue

        # Skip if no formula
        if not math_row.formula_text:
            logger.info(f"Skipping MathModel row {row_number} {math_row.initiative_key} with no formula")
            stats.skipped_row_mathmodeltab_invalid_formula += 1
            continue

        # Validate formula before extraction (avoid seeding junk)
        errors = validate_formula(math_row.formula_text)
        if errors:
            logger.info(
                f"Skipping MathModel row {row_number} {math_row.initiative_key} with invalid formula: {errors}"
            )
            stats.skipped_row_mathmodeltab_invalid_formula += 1
            continue

        # Extract identifiers from approved formula
        try:
            identifiers = extract_identifiers(math_row.formula_text)
        except Exception as exc:
            logger.warning(
                f"Failed to extract identifiers from formula at row {row_number}: {exc}"
            )
            stats.skipped_row_mathmodeltab_invalid_formula += 1
            continue

        if not identifiers:
            logger.info(f"Skipping MathModel row {row_number} {math_row.initiative_key} with no identifiers")
            stats.skipped_row_mathmodeltab_no_identifiers += 1
            continue
        # Find missing identifiers (for MATH_MODEL framework only) and dedupe
        missing_identifiers = sorted(
            {
                ident
                for ident in identifiers
                if (math_row.initiative_key, "MATH_MODEL", ident) not in existing_keys
            }
        )

        if not missing_identifiers:
            logger.info(
                f"No missing identifiers for MathModel row {row_number}, skipping"
            )
            stats.skipped_row_mathmodeltab_no_missing += 1
            continue

        stats.eligible_rows_mathmodelstab += 1

        # Check LLM call limit
        if stats.llm_calls >= max_llm_calls:
            logger.warning(
                f"Reached max_llm_calls limit ({max_llm_calls}), stopping"
            )
            break

        # Call LLM for param metadata (with formula context for quality)
        logger.info(
            f"Calling LLM for {len(missing_identifiers)} identifiers "
            f"in {math_row.initiative_key}"
        )
        try:
            suggestion = suggest_param_metadata_for_model(
                initiative_key=math_row.initiative_key,
                identifiers=missing_identifiers,
                formula_text=math_row.formula_text,
                llm=llm_client,
            )
            stats.llm_calls += 1
        except Exception as exc:
            logger.exception(
                f"LLM call failed for {math_row.initiative_key}: {exc}"
            )
            continue

        # Build params to append
        params_to_append = []
        seen_keys = set()
        for param_sugg in suggestion.params:
            # Only append if identifier was in missing list
            if param_sugg.key not in missing_identifiers:
                logger.info(
                    f"LLM returned param '{param_sugg.key}' not in missing identifiers, skipping"
                )
                continue

            # Avoid duplicates within the same run
            if param_sugg.key in seen_keys:
                logger.info(
                    f"Duplicate LLM param suggestion '{param_sugg.key}' for "
                    f"{math_row.initiative_key}, skipping"
                )
                continue
            seen_keys.add(param_sugg.key)

            # Store example value in notes if present; keep value empty for PM to fill
            notes = f"LLM example: {param_sugg.example_value}" if param_sugg.example_value else ""

            params_to_append.append(
                {
                    "initiative_key": math_row.initiative_key,
                    "param_name": param_sugg.key,
                    "param_display": param_sugg.name or param_sugg.key,
                    "description": param_sugg.description or "",
                    "unit": param_sugg.unit or "",
                    "source": param_sugg.source_hint or "ai_suggested",
                    "value": "",  # Empty: PM/Finance fills this
                    "approved": False,
                    "is_auto_seeded": True,
                    "framework": "MATH_MODEL",
                    "notes": notes,
                }
            )

        if params_to_append:
            params_writer.append_new_params(
                spreadsheet_id=spreadsheet_id,
                tab_name=params_tab,
                params=params_to_append,
            )
            stats.seeded_params_paramsstab += len(params_to_append)
            logger.info(
                f"Seeded {len(params_to_append)} params for {math_row.initiative_key}"
            )

    logger.info(f"Param seeding completed: {stats.summary()}")
    return stats
