# productroadmap_sheet_project/app/sheets/math_models_writer.py

"""MathModels sheet writer for ProductOps sheet.

Writes LLM suggestions to separate columns in the MathModels tab.
Never overwrites user-approved cells.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
import logging
from datetime import datetime, timezone

from app.sheets.client import SheetsClient
from app.sheets.models import MATHMODELS_HEADER_MAP
from app.utils.header_utils import normalize_header
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MathModelsWriter:
    """Writer for LLM suggestions in MathModels tab.
    
    Strategy:
    - llm_suggested_formula_text column: populated by LLM, never overwrites
    - llm_notes column: populated by LLM, never overwrites
    - Never updates formula_text, assumptions_text, or approved fields
      if approved_by_user is True
    
    This prevents overwriting human-made changes while still providing
    LLM suggestions side-by-side.
    """
    
    def __init__(self, client: SheetsClient) -> None:
        self.client = client
    
    def write_formula_suggestion(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_number: int,
        llm_suggested_formula_text: str,
    ) -> None:
        """Write a formula suggestion to the llm_suggested_formula_text column."""
        col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_formula_text")
        if not col_idx:
            logger.warning(f"Could not find llm_suggested_formula_text column in {tab_name}")
            return
        
        col_a1 = _col_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        
        self.client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=cell_a1,
            values=[[llm_suggested_formula_text]],
            value_input_option="RAW",
        )

        # Stamp provenance if Updated Source column exists
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        if us_col_idx or ua_col_idx:
            updates = []
            if us_col_idx:
                us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                updates.append({"range": us_a1, "values": [[token(Provenance.FLOW4_SUGGEST_MATHMODELS)]]})
            if ua_col_idx:
                ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                updates.append({"range": ua_a1, "values": [[_now_iso()]]})
            if updates:
                self.client.batch_update_values(
                    spreadsheet_id=spreadsheet_id,
                    data=updates,
                    value_input_option="RAW",
                )
    
    def write_llm_notes(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_number: int,
        llm_notes: str,
    ) -> None:
        """Write LLM notes/assumptions to the llm_notes column."""
        col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_notes")
        if not col_idx:
            logger.warning(f"Could not find llm_notes column in {tab_name}")
            return
        
        col_a1 = _col_index_to_a1(col_idx)
        cell_a1 = f"{tab_name}!{col_a1}{row_number}"
        
        self.client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=cell_a1,
            values=[[llm_notes]],
            value_input_option="RAW",
        )

        # Stamp provenance if Updated Source column exists
        us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        if us_col_idx or ua_col_idx:
            updates = []
            if us_col_idx:
                us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                updates.append({"range": us_a1, "values": [[token(Provenance.FLOW4_SUGGEST_MATHMODELS)]]})
            if ua_col_idx:
                ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                updates.append({"range": ua_a1, "values": [[_now_iso()]]})
            if updates:
                self.client.batch_update_values(
                    spreadsheet_id=spreadsheet_id,
                    data=updates,
                    value_input_option="RAW",
                )
    
    def write_suggestions_batch(
        self,
        spreadsheet_id: str,
        tab_name: str,
        suggestions: List[Dict[str, Any]],
    ) -> None:
        """Batch write multiple suggestions in a single API call.
        
        CRITICAL: Re-checks approved_by_user before writing to prevent race conditions
        where PM approves during job execution.
        
        Each suggestion dict should have:
        {
            "row_number": int,
            "llm_suggested_formula_text": Optional[str],
            "llm_notes": Optional[str],
            "llm_suggested_metric_chain_text": Optional[str],
            "constructed_llm_prompt": Optional[str],
            "llm_evaluation_score": Optional[int],
            "llm_evaluation_verdict": Optional[str],
            "llm_evaluation_issues": Optional[str],
            "llm_evaluation_strengths": Optional[str],
            "llm_evaluation_suggested_improvements": Optional[str],
            "llm_selected_target_kpi": Optional[str],
            "llm_target_kpi_reasoning": Optional[str],
            "llm_revision_attempts": Optional[int],
        }
        
        NOTE: We do NOT write assumptions_text—that is user-owned. PM edits assumptions manually.
        """
        if not suggestions:
            return
        
        # Find column indices
        formula_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_formula_text")
        notes_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_notes")
        metric_chain_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_suggested_metric_chain_text")
        prompt_col_idx = self._find_column_index(spreadsheet_id, tab_name, "constructed_llm_prompt")
        evaluation_score_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_evaluation_score")
        evaluation_verdict_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_evaluation_verdict")
        evaluation_issues_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_evaluation_issues")
        evaluation_strengths_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_evaluation_strengths")
        evaluation_improvements_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_evaluation_suggested_improvements")
        selected_target_kpi_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_selected_target_kpi")
        target_kpi_reasoning_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_target_kpi_reasoning")
        revision_attempts_col_idx = self._find_column_index(spreadsheet_id, tab_name, "llm_revision_attempts")
        approved_col_idx = self._find_column_index(spreadsheet_id, tab_name, "approved_by_user")
        suggested_by_llm_col_idx = self._find_column_index(spreadsheet_id, tab_name, "suggested_by_llm")
        
        # Guard: require at least one suggestion column
        if not (
            formula_col_idx
            or notes_col_idx
            or metric_chain_col_idx
            or prompt_col_idx
            or evaluation_score_col_idx
            or evaluation_verdict_col_idx
            or evaluation_issues_col_idx
            or evaluation_strengths_col_idx
            or evaluation_improvements_col_idx
            or selected_target_kpi_col_idx
            or target_kpi_reasoning_col_idx
            or revision_attempts_col_idx
        ):
            logger.warning(f"Could not find suggestion columns in {tab_name}")
            return
        
        # Race-safety: fetch current approved status before writing
        row_numbers: List[int] = []
        for s in suggestions:
            row_num = s.get("row_number")
            if isinstance(row_num, int):
                row_numbers.append(row_num)
        approved_map = {}
        if approved_col_idx and row_numbers:
            approved_map = self._get_approved_status_for_rows(
                spreadsheet_id,
                tab_name,
                row_numbers,
                approved_col_idx,
            )
        elif not approved_col_idx and row_numbers:
            logger.warning(f"Could not find approved_by_user column in {tab_name}; skipping race-safety check")
        
        # Build batch update data and track which rows were actually updated
        batch_data = []
        updated_rows = set()  # Track rows that had at least one cell written
        ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
        
        for suggestion in suggestions:
            row_number = suggestion.get("row_number")
            
            # Guard: row_number must be int
            if not isinstance(row_number, int):
                logger.warning("mathmodels.write.skip_bad_row_number", extra={"row_number": row_number})
                continue
            
            formula_sugg = suggestion.get("llm_suggested_formula_text")
            notes_sugg = suggestion.get("llm_notes")
            metric_chain_sugg = suggestion.get("llm_suggested_metric_chain_text")
            constructed_prompt = suggestion.get("constructed_llm_prompt")
            evaluation_score = suggestion.get("llm_evaluation_score")
            evaluation_verdict = suggestion.get("llm_evaluation_verdict")
            evaluation_issues = suggestion.get("llm_evaluation_issues")
            evaluation_strengths = suggestion.get("llm_evaluation_strengths")
            evaluation_improvements = suggestion.get("llm_evaluation_suggested_improvements")
            selected_target_kpi = suggestion.get("llm_selected_target_kpi")
            target_kpi_reasoning = suggestion.get("llm_target_kpi_reasoning")
            revision_attempts = suggestion.get("llm_revision_attempts")

            row_is_approved = approved_map.get(row_number, False)
            has_audit_only_write = any(
                value is not None and value != ""
                for value in (
                    constructed_prompt,
                    evaluation_score,
                    evaluation_verdict,
                    evaluation_issues,
                    evaluation_strengths,
                    evaluation_improvements,
                    selected_target_kpi,
                    target_kpi_reasoning,
                    revision_attempts,
                )
            )
            if row_is_approved and not has_audit_only_write:
                logger.info("mathmodels.write.skip_approved", extra={"row": row_number})
                continue
            
            if formula_col_idx and formula_sugg and not row_is_approved:
                col_a1 = _col_index_to_a1(formula_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[formula_sugg]],
                })
                updated_rows.add(row_number)

            if notes_col_idx and notes_sugg and not row_is_approved:
                col_a1 = _col_index_to_a1(notes_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[notes_sugg]],
                })
                updated_rows.add(row_number)

            if metric_chain_col_idx and metric_chain_sugg and not row_is_approved:
                col_a1 = _col_index_to_a1(metric_chain_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[metric_chain_sugg]],
                })
                updated_rows.add(row_number)

            if prompt_col_idx and constructed_prompt:
                col_a1 = _col_index_to_a1(prompt_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[constructed_prompt]],
                })
                updated_rows.add(row_number)

            if evaluation_score_col_idx and evaluation_score is not None:
                col_a1 = _col_index_to_a1(evaluation_score_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[evaluation_score]]})
                updated_rows.add(row_number)

            if evaluation_verdict_col_idx and evaluation_verdict:
                col_a1 = _col_index_to_a1(evaluation_verdict_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[evaluation_verdict]]})
                updated_rows.add(row_number)

            if evaluation_issues_col_idx and evaluation_issues is not None:
                col_a1 = _col_index_to_a1(evaluation_issues_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[evaluation_issues]]})
                updated_rows.add(row_number)

            if evaluation_strengths_col_idx and evaluation_strengths is not None:
                col_a1 = _col_index_to_a1(evaluation_strengths_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[evaluation_strengths]]})
                updated_rows.add(row_number)

            if evaluation_improvements_col_idx and evaluation_improvements is not None:
                col_a1 = _col_index_to_a1(evaluation_improvements_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[evaluation_improvements]]})
                updated_rows.add(row_number)

            if selected_target_kpi_col_idx and selected_target_kpi is not None:
                col_a1 = _col_index_to_a1(selected_target_kpi_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[selected_target_kpi]]})
                updated_rows.add(row_number)

            if target_kpi_reasoning_col_idx and target_kpi_reasoning is not None:
                col_a1 = _col_index_to_a1(target_kpi_reasoning_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[target_kpi_reasoning]]})
                updated_rows.add(row_number)

            if revision_attempts_col_idx and revision_attempts is not None:
                col_a1 = _col_index_to_a1(revision_attempts_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({"range": cell_a1, "values": [[revision_attempts]]})
                updated_rows.add(row_number)


            # Mark as suggested by LLM if any suggestion was provided
            if suggested_by_llm_col_idx and (
                formula_sugg
                or notes_sugg
                or metric_chain_sugg
                or constructed_prompt
                or evaluation_score is not None
                or evaluation_verdict
            ):
                col_a1 = _col_index_to_a1(suggested_by_llm_col_idx)
                cell_a1 = f"{tab_name}!{col_a1}{row_number}"
                batch_data.append({
                    "range": cell_a1,
                    "values": [[True]],
                })
                updated_rows.add(row_number)
        
        if batch_data:
            # If Updated Source column exists, add provenance token ONLY for rows that were actually updated
            us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
            if us_col_idx or ua_col_idx:
                ts = _now_iso()
                for row_number in updated_rows:
                    if us_col_idx:
                        us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                        batch_data.append({
                            "range": us_a1,
                            "values": [[token(Provenance.FLOW4_SUGGEST_MATHMODELS)]],
                        })
                    if ua_col_idx:
                        ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                        batch_data.append({
                            "range": ua_a1,
                            "values": [[ts]],
                        })

            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
    
    def _find_column_index(
        self,
        spreadsheet_id: str,
        tab_name: str,
        column_name: str,
    ) -> Optional[int]:
        """Find the 1-based column index for a given column name.
        
        Uses MATHMODELS_HEADER_MAP to check for all known aliases.
        """
        header_row = 1
        range_a1 = f"{tab_name}!{header_row}:{header_row}"
        
        try:
            values = self.client.get_values(spreadsheet_id, range_a1)
            if not values:
                return None
            
            headers = values[0]
            
            # Get all aliases for this canonical column name
            aliases = MATHMODELS_HEADER_MAP.get(column_name, [column_name])
            normalized_aliases = [normalize_header(a) for a in aliases]
            
            for i, h in enumerate(headers, start=1):
                if h is None:
                    continue
                if normalize_header(str(h)) in normalized_aliases:
                    return i
            
            return None
        except Exception as e:
            logger.error(f"Error finding column {column_name} in {tab_name}: {e}")
            return None
    
    def _get_approved_status_for_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_numbers: List[int],
        approved_col_idx: int,
    ) -> Dict[int, bool]:
        """Fetch approved_by_user status for rows in a single range query.
        
        Returns dict mapping row_number -> approved_by_user value.
        Used to prevent race conditions where PM approves during job execution.
        
        Optimization: Fetches a single continuous range instead of N individual calls.
        """
        if not row_numbers or not approved_col_idx:
            return {}
        
        try:
            col_a1 = _col_index_to_a1(approved_col_idx)
            min_row = min(row_numbers)
            max_row = max(row_numbers)
            
            # Fetch continuous range covering all rows
            range_a1 = f"{tab_name}!{col_a1}{min_row}:{col_a1}{max_row}"
            values = self.client.get_values(spreadsheet_id, range_a1)
            
            # Map back to row numbers
            result = {}
            if values:
                for offset, cell_val in enumerate(values):
                    row_num = min_row + offset
                    if row_num in row_numbers:
                        # True if cell is "TRUE", "true", "1", etc.
                        if cell_val:
                            cell_str = str(cell_val[0] if isinstance(cell_val, list) else cell_val).strip().lower()
                            result[row_num] = cell_str in ("true", "1", "yes")
                        else:
                            result[row_num] = False
            
            # Fill in any missing rows as False
            for row_num in row_numbers:
                if row_num not in result:
                    result[row_num] = False
            
            return result
        except Exception as e:
            logger.error(f"Error fetching approved status in {tab_name}: {e}")
            return {}


    def write_computed_scores_batch(
        self,
        spreadsheet_id: str,
        tab_name: str,
        scores: List[Dict[str, Any]],
    ) -> int:
        """Batch write computed_score values to MathModels tab.
        
        Each score dict should have:
        {
            "row_number": int,
            "computed_score": float | None,
        }
        
        Returns number of cells updated.
        """
        if not scores:
            return 0
        
        # Find computed_score column index
        computed_col_idx = self._find_column_index(spreadsheet_id, tab_name, "computed_score")
        if not computed_col_idx:
            logger.warning(f"Could not find computed_score column in {tab_name}")
            return 0
        
        # Build batch update data
        batch_data = []
        updated_rows = set()
        
        for score_entry in scores:
            row_number = score_entry.get("row_number")
            computed_score = score_entry.get("computed_score")
            
            if not isinstance(row_number, int):
                logger.warning("mathmodels.write_score.skip_bad_row_number", extra={"row_number": row_number})
                continue
            
            # Write computed_score (even if None, to clear stale values)
            col_a1 = _col_index_to_a1(computed_col_idx)
            cell_a1 = f"{tab_name}!{col_a1}{row_number}"
            
            # Format score value (round to reasonable precision or empty if None)
            cell_value = round(computed_score, 4) if computed_score is not None else ""
            
            batch_data.append({
                "range": cell_a1,
                "values": [[cell_value]],
            })
            updated_rows.add(row_number)
        
        if batch_data:
            # Add provenance stamps
            us_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_source")
            ua_col_idx = self._find_column_index(spreadsheet_id, tab_name, "updated_at")
            
            if us_col_idx or ua_col_idx:
                ts = _now_iso()
                for row_number in updated_rows:
                    if us_col_idx:
                        us_a1 = f"{tab_name}!{_col_index_to_a1(us_col_idx)}{row_number}"
                        batch_data.append({
                            "range": us_a1,
                            "values": [[token(Provenance.FLOW3_MATHMODELS_WRITE_COMPUTED_SCORES)]],
                        })
                    if ua_col_idx:
                        ua_a1 = f"{tab_name}!{_col_index_to_a1(ua_col_idx)}{row_number}"
                        batch_data.append({
                            "range": ua_a1,
                            "values": [[ts]],
                        })
            
            self.client.batch_update_values(
                spreadsheet_id=spreadsheet_id,
                data=batch_data,
                value_input_option="RAW",
            )
        
        return len(updated_rows)


def _col_index_to_a1(idx: int) -> str:
    """Convert 1-based column index to A1 letter(s)."""
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def write_computed_scores_to_mathmodels_sheet(
    db: "Session",
    client: SheetsClient,
    spreadsheet_id: str,
    tab_name: str = "MathModels",
    *,
    initiative_keys: Optional[List[str]] = None,
) -> int:
    """Write computed_score from DB back to MathModels sheet.
    
    This is a DB → Sheet writeback for computed_score after scoring.
    Matches sheet rows to DB records by (initiative_key, model_name).
    
    Args:
        db: Database session
        client: SheetsClient instance
        spreadsheet_id: Product Ops spreadsheet ID
        tab_name: Sheet tab name (default: "MathModels")
        initiative_keys: Optional list of initiative keys to write (None = all)
    
    Returns:
        Number of rows with computed_score written
    """
    from app.db.models.initiative import Initiative
    from app.db.models.scoring import InitiativeMathModel
    from app.sheets.math_models_reader import MathModelsReader
    
    # Step 1: Read sheet rows to get row_number + (initiative_key, model_name) mapping
    reader = MathModelsReader(client)
    sheet_rows = reader.get_rows_for_sheet(spreadsheet_id, tab_name)
    
    if not sheet_rows:
        logger.debug("mathmodels_writer.write_scores.no_sheet_rows", extra={"tab": tab_name})
        return 0
    
    # Build lookup: (initiative_key, model_name) -> row_number
    row_lookup: Dict[Tuple[str, str], int] = {}
    for row_number, row in sheet_rows:
        key = row.initiative_key
        name = row.model_name or ""
        if key:
            row_lookup[(key, name)] = row_number
    
    # Step 2: Query DB for math models with computed_score
    query = db.query(InitiativeMathModel).join(Initiative)
    if initiative_keys:
        query = query.filter(Initiative.initiative_key.in_(initiative_keys))
    
    db_models = query.all()
    
    if not db_models:
        logger.debug("mathmodels_writer.write_scores.no_db_models")
        return 0
    
    # Step 3: Build list of scores to write
    scores_to_write: List[Dict[str, Any]] = []
    for model in db_models:
        ini_key = model.initiative.initiative_key if model.initiative else None
        model_name = str(model.model_name or "")
        
        if not ini_key:
            continue
        
        row_number = row_lookup.get((str(ini_key), model_name))
        if row_number is None:
            logger.debug(
                "mathmodels_writer.write_scores.no_matching_row",
                extra={"initiative_key": ini_key, "model_name": model_name},
            )
            continue
        
        scores_to_write.append({
            "row_number": row_number,
            "computed_score": model.computed_score,
        })
    
    if not scores_to_write:
        logger.debug("mathmodels_writer.write_scores.no_scores_to_write")
        return 0
    
    # Step 4: Write to sheet
    writer = MathModelsWriter(client)
    written = writer.write_computed_scores_batch(spreadsheet_id, tab_name, scores_to_write)
    
    logger.info(
        "mathmodels_writer.write_scores.done",
        extra={"written": written, "total_models": len(db_models)},
    )
    
    return written
