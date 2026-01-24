#productroadmap_sheet_project/app/services/kpi_contributions_sync_service.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.db.models.optimization import OrganizationMetricConfig
from app.sheets.client import SheetsClient
from app.sheets.kpi_contributions_reader import KPIContributionsReader, ContribRowPair
from app.utils.provenance import Provenance, token

logger = logging.getLogger(__name__)


class KPIContributionsSyncService:
    """Sheet → DB sync for ProductOps KPI_Contributions tab."""

    def __init__(self, client: SheetsClient) -> None:
        self.client = client
        self.reader = KPIContributionsReader(client)

    def preview_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        max_rows: Optional[int] = None,
    ) -> List[ContribRowPair]:
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
        rows = self.reader.get_rows_for_sheet(spreadsheet_id, tab_name)

        if initiative_keys is not None:
            allowed_keys = {k for k in initiative_keys if k}
            rows = [(row_num, r) for row_num, r in rows if r.initiative_key in allowed_keys]

        allowed_kpis = self._load_allowed_kpis(db)
        upserts = 0
        unlocked = 0
        skipped_no_initiative = 0
        skipped_invalid_json = 0
        skipped_disallowed_kpi = 0
        skipped_empty = 0

        batch_count = 0
        for _, row in rows:
            initiative: Initiative | None = (
                db.query(Initiative)
                .filter(Initiative.initiative_key == row.initiative_key)
                .one_or_none()
            )
            if not initiative:
                skipped_no_initiative += 1
                continue

            contrib = self._normalize_contribution(row.kpi_contribution_json)
            if contrib is None:
                # FIX #2: Treat empty/cleared kpi_contribution_json as explicit unlock
                # PM cleared the field → unlock override, let system take control again
                current_source = getattr(initiative, "kpi_contribution_source", None)
                if current_source == "pm_override":
                    initiative.kpi_contribution_json = None  # type: ignore[assignment]
                    initiative.kpi_contribution_source = None  # type: ignore[assignment]
                    initiative.updated_source = token(Provenance.FLOW5_SYNC_KPI_CONTRIBUTIONS)  # type: ignore[assignment]
                    unlocked += 1
                    batch_count += 1
                    if batch_count >= commit_every:
                        db.commit()
                        batch_count = 0
                    logger.info(
                        "kpi_contrib_sync.unlock_override",
                        extra={"initiative_key": row.initiative_key},
                    )
                else:
                    skipped_empty += 1
                continue

            invalid_keys = [k for k in contrib.keys() if k not in allowed_kpis]
            if invalid_keys:
                skipped_disallowed_kpi += 1
                logger.warning(
                    "kpi_contrib_sync.disallowed_keys",
                    extra={"initiative_key": row.initiative_key, "invalid_keys": invalid_keys},
                )
                continue

            if not self._values_are_numeric(contrib):
                skipped_invalid_json += 1
                logger.warning(
                    "kpi_contrib_sync.non_numeric_values",
                    extra={"initiative_key": row.initiative_key},
                )
                continue

            initiative.kpi_contribution_json = contrib  # type: ignore[assignment]
            initiative.kpi_contribution_source = "pm_override"  # type: ignore[attr-defined]
            initiative.updated_source = token(Provenance.FLOW5_SYNC_KPI_CONTRIBUTIONS)  # type: ignore[assignment]

            upserts += 1
            batch_count += 1
            if batch_count >= commit_every:
                db.commit()
                batch_count = 0

        if batch_count:
            db.commit()

        return {
            "row_count": len(rows),
            "upserts": upserts,
            "unlocked": unlocked,
            "skipped_no_initiative": skipped_no_initiative,
            "skipped_invalid_json": skipped_invalid_json,
            "skipped_disallowed_kpi": skipped_disallowed_kpi,
            "skipped_empty": skipped_empty,
            "allowed_kpis": sorted(list(allowed_kpis)),
        }

    def _load_allowed_kpis(self, db: Session) -> set[str]:
        configs: List[OrganizationMetricConfig] = db.query(OrganizationMetricConfig).all()
        allowed: set[str] = set()
        for cfg in configs:
            meta = cfg.metadata_json or {}
            is_active = meta.get("is_active", True)
            if not is_active:
                continue
            if cfg.kpi_level not in {"north_star", "strategic"}:
                continue
            key = cast(str, cfg.kpi_key)
            if key:
                allowed.add(key)
        return allowed

    def _normalize_contribution(self, raw: Any) -> Optional[Dict[str, float]]:
        if raw is None:
            return None
        obj = raw
        if isinstance(raw, str):
            try:
                obj = json.loads(raw)
            except Exception:
                return None
        if not isinstance(obj, dict):
            return None
        clean: Dict[str, float] = {}
        for k, v in obj.items():
            if v is None:
                continue
            try:
                clean[str(k)] = float(v)
            except (TypeError, ValueError):
                return None
        return clean if clean else None

    def _values_are_numeric(self, contrib: Dict[str, float]) -> bool:
        return all(isinstance(v, (int, float)) for v in contrib.values())


__all__ = ["KPIContributionsSyncService"]
