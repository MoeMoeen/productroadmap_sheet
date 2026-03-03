# productroadmap_sheet_project/app/sheets/instructions_registry.py
"""Registry of per-tab instruction copy for system-managed instruction rows.

This keeps the UI text in-source (per sheet type + tab) so we can render
instructions deterministically onto sheets without manual edits.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


logger = logging.getLogger("app.sheets.instructions_registry")


def _normalize_tab_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


@dataclass(frozen=True)
class TabInstructions:
    tab_name: str  # Exact Google Sheet tab name
    title: str     # Display title inside the instructions text
    lines: Tuple[str, ...]
    actions: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


SheetType = str
TabName = str

# Registry key = (sheet_type, tab_name_lower)
INSTRUCTIONS_REGISTRY: Dict[Tuple[SheetType, TabName], TabInstructions] = {
    # Optimization Center
    ("optimization_center", "settings"): TabInstructions(
        tab_name="Settings",
        title="Settings",
        lines=(
            "Set current_scenario_name and current_constraint_set_name used by menu actions.",
            "Optionally set candidates_data_start_row if you change reserved rows.",
        ),
        actions=("pm.refresh_sheet_instructions",),
    ),
    ("optimization_center", "candidates"): TabInstructions(
        tab_name="Candidates",
        title="Candidates",
        lines=(
            "Candidate / selection surface.",
            "Select items using is_selected_for_run (or select rows explicitly).",
            "Edit constraints only in Constraints/Targets tabs; this tab shows derived indicators.",
            "Suggested flow: Save → Populate → Run → Explain.",
        ),
        actions=(
            "pm.save_optimization",
            "pm.populate_candidates",
            "pm.optimize_run_selected_candidates",
            "pm.explain_selection",
        ),
        warnings=(
            "If constraint-derived fields look stale, run Save (or Run/Explain) to sync Constraints → DB first.",
        ),
    ),
    ("optimization_center", "scenario_config"): TabInstructions(
        tab_name="Scenario_Config",
        title="Scenario_Config",
        lines=(
            "Define scenario parameters (capacity_total_tokens, objective_mode, objective_weights_json).",
            "Run Save current tab → DB after edits.",
        ),
        actions=("pm.save_optimization",),
    ),
    ("optimization_center", "constraints"): TabInstructions(
        tab_name="Constraints",
        title="Constraints",
        lines=(
            "Authoritative entry surface for constraints (mandatory, bundles, prereqs, exclusions, caps/floors).",
            "Run Save current tab → DB after edits.",
        ),
        actions=("pm.save_optimization",),
    ),
    ("optimization_center", "targets"): TabInstructions(
        tab_name="Targets",
        title="Targets",
        lines=(
            "Authoritative entry surface for KPI targets (floors/goals).",
            "Run Save current tab → DB after edits.",
        ),
        actions=("pm.save_optimization",),
    ),
    ("optimization_center", "runs"): TabInstructions(
        tab_name="Runs",
        title="Runs",
        lines=(
            "System log of optimization runs (append-only).",
            "Use as an audit trail. Do not edit system columns.",
        ),
        actions=("pm.optimize_run_selected_candidates", "pm.optimize_run_all_candidates"),
    ),
    ("optimization_center", "results"): TabInstructions(
        tab_name="Results",
        title="Results",
        lines=(
            "System output of selected portfolio items per run.",
            "Do not edit system columns. Notes may be PM-owned if enabled.",
        ),
    ),
    ("optimization_center", "gaps_and_alerts"): TabInstructions(
        tab_name="Gaps_and_Alerts",
        title="Gaps & Alerts",
        lines=(
            "System output of unmet targets/caps/floors (diagnostics).",
            "Use Explain Selection for repair suggestions on a specific selection.",
        ),
        actions=("pm.explain_selection",),
    ),
}


def get_tab_instructions(sheet_type: str, tab_name: str) -> Optional[TabInstructions]:
    key = (_normalize_tab_key(sheet_type), _normalize_tab_key(tab_name))
    return INSTRUCTIONS_REGISTRY.get(key)


def validate_registry(strict: Optional[bool] = None) -> None:
    """Dev-time guard to catch typos/alias mismatches early.

    strict=None → decide based on ENV (default strict for dev/test, soft for prod).
    """
    if strict is None:
        env = "dev"
        try:
            from app.config import settings  # local import to avoid cycles
            env = (settings.ENV or "dev").strip().lower()
        except Exception:
            pass
        strict = env in {"dev", "test", "ci", "local"}

    errors = []
    for (stype, tab_key), ins in INSTRUCTIONS_REGISTRY.items():
        tn = (ins.tab_name or "").strip()
        if not tn:
            errors.append(f"TabInstructions missing tab_name for sheet_type={stype}, key={tab_key}")
            continue
        norm_tn = _normalize_tab_key(tn)
        if tab_key != norm_tn:
            errors.append(
                f"Registry key tab '{tab_key}' does not match tab_name '{ins.tab_name}' (norm='{norm_tn}') for sheet_type={stype}"
            )

    if errors:
        msg = "; ".join(errors)
        if strict:
            raise ValueError(msg)
        logger.error("instructions_registry.validation_failed", extra={"errors": errors})


# Run validation at import time to avoid silent skips in refresh actions.
validate_registry()
