#productroadmap_sheet_project/app/services/initiative_summary_service.py
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Optional, cast

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeMathModel
from app.llm.client import LLMClient
from app.llm.scoring_assistant import load_sheet_level_llm_context
from app.llm.models import InitiativeSummaryMathModelInput, InitiativeSummaryOutput, InitiativeSummaryPromptInput
from app.sheets.backlog_reader import BacklogReader, BacklogRow
from app.sheets.backlog_writer import write_llm_summaries_to_backlog_sheet
from app.sheets.client import SheetsClient
from app.utils.header_utils import get_value_by_header_alias


SUMMARY_UPDATED_SOURCE = "pm.generate_llm_summary"
SUMMARY_HASH_META_KEY = "_meta"
SUMMARY_INPUT_HASH_KEY = "input_hash"
SUMMARY_GENERATED_AT_KEY = "generated_at"
MAX_PARALLEL_SUMMARY_LLM_CALLS = 4
GENERIC_OPEN_QUESTION_SUBSTRINGS = (
    "what specific",
    "how will",
    "what data sources",
    "what metrics",
    "how do we measure",
    "how should we measure",
)


def build_initiative_summary_prompt_input(
    initiative: Initiative,
    backlog_row: Optional[BacklogRow],
    approved_math_model: Optional[InitiativeMathModel],
    *,
    llm_context_text: Optional[str] = None,
) -> InitiativeSummaryPromptInput:
    sheet_description = None
    if backlog_row:
        raw_description = get_value_by_header_alias(backlog_row, "Description", [])
        if raw_description is not None:
            sheet_description = str(raw_description).strip() or None

    approved_model_payload = None
    if approved_math_model is not None:
        approved_model_payload = InitiativeSummaryMathModelInput(
            model_name=getattr(approved_math_model, "model_name", None),
            target_kpi_key=getattr(approved_math_model, "target_kpi_key", None),
            metric_chain_text=getattr(approved_math_model, "metric_chain_text", None),
            formula_text=getattr(approved_math_model, "formula_text", None),
            assumptions_text=getattr(approved_math_model, "assumptions_text", None),
            model_description_free_text=getattr(approved_math_model, "model_description_free_text", None),
        )

    return InitiativeSummaryPromptInput(
        initiative_key=str(initiative.initiative_key),
        title=str(initiative.title),
        requesting_team=getattr(initiative, "requesting_team", None),
        product_area=getattr(initiative, "product_area", None),
        customer_segment=getattr(initiative, "customer_segment", None),
        initiative_type=getattr(initiative, "initiative_type", None),
        immediate_kpi_key=getattr(initiative, "immediate_kpi_key", None),
        problem_statement=getattr(initiative, "problem_statement", None),
        hypothesis=getattr(initiative, "hypothesis", None),
        sheet_description=sheet_description,
        dependencies_others=getattr(initiative, "dependencies_others", None),
        risk_description=getattr(initiative, "risk_description", None),
        approved_math_model=approved_model_payload,
        llm_context_text=llm_context_text,
    )


def choose_approved_math_model(initiative: Initiative) -> Optional[InitiativeMathModel]:
    approved_models = [
        model
        for model in getattr(initiative, "math_models", [])
        if getattr(model, "approved_by_user", False) and str(getattr(model, "formula_text", "") or "").strip()
    ]
    if not approved_models:
        return None

    def sort_key(model: InitiativeMathModel) -> tuple[int, float]:
        updated_at = cast(Optional[datetime], getattr(model, "updated_at", None))
        return (
            0 if getattr(model, "is_primary", False) else 1,
            -(updated_at.timestamp() if updated_at is not None else 0.0),
        )

    approved_models.sort(key=sort_key)
    return approved_models[0]


def format_initiative_summary_text(summary: InitiativeSummaryOutput) -> str:
    lines = [
        f"Headline: {summary.headline.strip()}",
        f"Opportunity: {summary.opportunity.strip()}",
        f"Proposed Solution: {summary.proposed_solution.strip()}",
        f"Expected Impact: {summary.expected_impact.strip()}",
    ]

    if summary.math_model_basis:
        lines.append(f"Math Model Basis: {summary.math_model_basis.strip()}")

    if summary.risks_and_dependencies:
        lines.append("Risks / Dependencies:")
        lines.extend(f"- {item.strip()}" for item in summary.risks_and_dependencies if item and item.strip())

    if summary.open_questions:
        lines.append("Open Questions:")
        lines.extend(f"- {item.strip()}" for item in summary.open_questions if item and item.strip())

    return "\n".join(lines)


def sanitize_summary_output(summary: InitiativeSummaryOutput) -> InitiativeSummaryOutput:
    def normalize_question(question: str) -> str:
        return " ".join(question.strip().split())

    filtered_questions: list[str] = []
    seen_questions: set[str] = set()
    for raw_question in summary.open_questions:
        question = normalize_question(raw_question)
        if not question:
            continue
        lowered = question.lower()
        if any(marker in lowered for marker in GENERIC_OPEN_QUESTION_SUBSTRINGS):
            continue
        if lowered in seen_questions:
            continue
        seen_questions.add(lowered)
        filtered_questions.append(question)

    filtered_risks: list[str] = []
    seen_risks: set[str] = set()
    for raw_risk in summary.risks_and_dependencies:
        risk = " ".join(raw_risk.strip().split())
        if not risk:
            continue
        lowered = risk.lower()
        if lowered in seen_risks:
            continue
        seen_risks.add(lowered)
        filtered_risks.append(risk)

    return summary.model_copy(
        update={
            "open_questions": filtered_questions,
            "risks_and_dependencies": filtered_risks,
        }
    )


def compute_summary_input_hash(payload: InitiativeSummaryPromptInput) -> str:
    payload_json = payload.model_dump(mode="json", exclude_none=True)
    payload_text = json.dumps(payload_json, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


def get_existing_summary_input_hash(initiative: Initiative) -> Optional[str]:
    existing_summary_text = cast(Optional[str], getattr(initiative, "llm_summary", None))
    if not existing_summary_text or not str(existing_summary_text).strip():
        return None

    summary_json = cast(Any, getattr(initiative, "llm_summary_json", None))
    if not isinstance(summary_json, dict):
        return None

    meta = summary_json.get(SUMMARY_HASH_META_KEY)
    if not isinstance(meta, dict):
        return None

    input_hash = meta.get(SUMMARY_INPUT_HASH_KEY)
    if isinstance(input_hash, str) and input_hash.strip():
        return input_hash.strip()
    return None


def build_summary_storage_json(summary: InitiativeSummaryOutput, input_hash: str) -> dict[str, Any]:
    payload = summary.model_dump(mode="json")
    payload[SUMMARY_HASH_META_KEY] = {
        SUMMARY_INPUT_HASH_KEY: input_hash,
        SUMMARY_GENERATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
    }
    return payload


class InitiativeSummaryService:
    def __init__(self, sheets_client: SheetsClient, llm_client: LLMClient) -> None:
        self.sheets_client = sheets_client
        self.llm_client = llm_client

    def generate_for_initiatives(
        self,
        *,
        db: Session,
        spreadsheet_id: str,
        tab_name: str,
        initiative_keys: list[str],
    ) -> Dict[str, Any]:
        reader = BacklogReader(self.sheets_client)
        backlog_rows = reader.get_rows(spreadsheet_id=spreadsheet_id, tab_name=tab_name)
        backlog_rows_by_key = {
            str(get_value_by_header_alias(row, "Initiative Key", []) or "").strip(): row
            for _, row in backlog_rows
        }
        llm_context_text = load_sheet_level_llm_context(
            self.sheets_client,
            spreadsheet_id=spreadsheet_id,
        )

        initiatives = (
            db.query(Initiative)
            .filter(Initiative.initiative_key.in_(initiative_keys))
            .all()
        )
        initiatives_by_key = {str(initiative.initiative_key): initiative for initiative in initiatives}

        summaries_by_key: Dict[str, str] = {}
        status_by_key: Dict[str, str] = {}
        ok_count = 0
        skipped_count = 0
        failed_count = 0
        skipped_unchanged_count = 0
        pending_generation: list[tuple[str, Initiative, InitiativeSummaryPromptInput, str]] = []

        for key in initiative_keys:
            initiative = initiatives_by_key.get(key)
            if initiative is None:
                status_by_key[key] = "FAILED: Initiative not found in DB"
                failed_count += 1
                continue

            backlog_row = backlog_rows_by_key.get(key)
            if backlog_row is None:
                status_by_key[key] = "SKIPPED: Initiative not found in Backlog"
                skipped_count += 1
                continue

            approved_math_model = choose_approved_math_model(initiative)
            payload = build_initiative_summary_prompt_input(
                initiative,
                backlog_row,
                approved_math_model,
                llm_context_text=llm_context_text,
            )
            input_hash = compute_summary_input_hash(payload)
            existing_input_hash = get_existing_summary_input_hash(initiative)

            if input_hash == existing_input_hash:
                status_by_key[key] = "SKIPPED: Summary input unchanged"
                skipped_count += 1
                skipped_unchanged_count += 1
                continue

            pending_generation.append((key, initiative, payload, input_hash))

        generated_by_key: dict[str, InitiativeSummaryOutput | Exception] = {}
        if pending_generation:
            max_workers = min(MAX_PARALLEL_SUMMARY_LLM_CALLS, len(pending_generation))
            if max_workers <= 1:
                key, _initiative, payload, _input_hash = pending_generation[0]
                try:
                    generated_by_key[key] = self.llm_client.generate_initiative_summary(payload)
                except Exception as exc:  # noqa: BLE001
                    generated_by_key[key] = exc
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_by_key = {
                        key: executor.submit(self.llm_client.generate_initiative_summary, payload)
                        for key, _initiative, payload, _input_hash in pending_generation
                    }
                    for key, future in future_by_key.items():
                        try:
                            generated_by_key[key] = future.result()
                        except Exception as exc:  # noqa: BLE001
                            generated_by_key[key] = exc

        for key, initiative, _payload, input_hash in pending_generation:
            generated = generated_by_key.get(key)
            if isinstance(generated, Exception) or generated is None:
                status_by_key[key] = "FAILED: LLM summary generation failed"
                failed_count += 1
                continue

            summary = sanitize_summary_output(generated)
            summary_text = format_initiative_summary_text(summary)
            initiative_row = cast(Any, initiative)
            initiative_row.llm_summary = summary_text
            initiative_row.llm_summary_json = build_summary_storage_json(summary, input_hash)
            initiative_row.updated_source = SUMMARY_UPDATED_SOURCE
            summaries_by_key[key] = summary_text
            status_by_key[key] = "OK"
            ok_count += 1

        if summaries_by_key:
            db.commit()
            sheet_updated = write_llm_summaries_to_backlog_sheet(
                self.sheets_client,
                spreadsheet_id,
                tab_name,
                summaries_by_key=summaries_by_key,
            )
        else:
            sheet_updated = 0

        return {
            "selected_count": len(initiative_keys),
            "ok_count": ok_count,
            "skipped_count": skipped_count,
            "skipped_unchanged_count": skipped_unchanged_count,
            "failed_count": failed_count,
            "sheet_updated": sheet_updated,
            "status_by_key": status_by_key,
        }
