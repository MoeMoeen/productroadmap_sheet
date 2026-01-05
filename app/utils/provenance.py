# projectroadmap_sheet_project/app/utils/provenance.py
from __future__ import annotations

from enum import Enum
from typing import Optional


class Provenance(str, Enum):
    """Canonical provenance tokens for DB and sheet writes."""

    # Flow 0: Intake
    FLOW0_INTAKE_SYNC = "flow0.intake_sync"

    # Flow 1: Backlog sheet read/write
    FLOW1_BACKLOGSHEET_READ = "flow1.backlogsheet_read"
    FLOW1_BACKLOGSHEET_WRITE = "flow1.backlogsheet_write"

    # Flow 2: Activation
    FLOW2_ACTIVATE = "flow2.activate"

    # Flow 3: ProductOps sheet read/write + compute
    FLOW3_PRODUCTOPSSHEET_READ_INPUTS = "flow3.productopssheet_read_inputs"
    FLOW3_COMPUTE_ALL_FRAMEWORKS = "flow3.compute_all_frameworks"
    FLOW3_PRODUCTOPSSHEET_WRITE_SCORES = "flow3.productopssheet_write_scores"

    # Flow 4: Math Models + Params
    FLOW4_SYNC_MATHMODELS = "flow4.sync_mathmodels"
    FLOW4_SYNC_PARAMS = "flow4.sync_params"
    FLOW4_SUGGEST_MATHMODELS = "flow4.suggest_mathmodels"
    FLOW4_SEED_PARAMS = "flow4.seed_params"
    FLOW4_PROTECT_SHEETS = "flow4.protect_sheets"

    # Flow 5: KPI registry + contributions
    FLOW5_SYNC_METRICS_CONFIG = "flow5.sync_metrics_config"
    FLOW5_SYNC_KPI_CONTRIBUTIONS = "flow5.sync_kpi_contributions"

    # Flow 6: Optimization Center sheets
    FLOW6_SYNC_OPT_CENTER = "flow6.sync_opt_center"


def token(prov: Provenance, run_id: Optional[str] = None) -> str:
    """Render a provenance token, optionally appending a run identifier later if needed."""

    return prov.value if not run_id else f"{prov.value}#{run_id}"


__all__ = ["Provenance", "token"]
