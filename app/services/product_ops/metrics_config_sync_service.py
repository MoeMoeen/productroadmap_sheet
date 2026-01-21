#productroadmap_sheet_project/app/services/metrics_config_sync_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.db.models.optimization import OrganizationMetricConfig
from app.sheets.client import SheetsClient
from app.sheets.metrics_config_reader import MetricsConfigReader, MetricRowPair

logger = logging.getLogger(__name__)


class MetricsConfigSyncService:
    """Sheet → DB sync for ProductOps Metrics_Config tab."""
    def __init__(self, client: SheetsClient) -> None:
        self.client = client
        self.reader = MetricsConfigReader(client)

    def preview_rows(
        self,
        spreadsheet_id: str,
        tab_name: str,
        max_rows: Optional[int] = None,
    ) -> List[MetricRowPair]:
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
        kpi_keys: Optional[List[str]] = None,
    ) -> dict:
        rows = self.reader.get_rows_for_sheet(spreadsheet_id, tab_name)

        allowed_keys: Set[str] | None = None
        if kpi_keys:
            allowed_keys = {k for k in kpi_keys if k}
            rows = [(row_num, r) for row_num, r in rows if r.kpi_key in allowed_keys]

        # Hard validations before mutating DB
        self._validate_unique_keys(rows)
        self._validate_active_north_star(rows)

        upserts = 0
        created = 0
        skipped_bad_level = 0
        batch_count = 0

        for _, row in rows:
            if row.kpi_level not in {"north_star", "strategic"}:
                skipped_bad_level += 1
                continue

            mc: OrganizationMetricConfig | None = (
                db.query(OrganizationMetricConfig)
                .filter(OrganizationMetricConfig.kpi_key == row.kpi_key)
                .one_or_none()
            )

            created_now = False
            if not mc:
                mc = OrganizationMetricConfig(kpi_key=row.kpi_key)
                db.add(mc)
                created_now = True

            mc.kpi_name = row.kpi_name or mc.kpi_name or row.kpi_key  # type: ignore[assignment]
            mc.kpi_level = row.kpi_level  # type: ignore[assignment]
            mc.unit = row.unit or mc.unit  # type: ignore[assignment]

            metadata: Dict[str, Any] = dict(mc.metadata_json or {})  # type: ignore[arg-type]
            if row.description is not None:
                metadata["description"] = row.description
            if row.notes is not None:
                metadata["notes"] = row.notes
            if row.is_active is not None:
                metadata["is_active"] = bool(row.is_active)
            elif "is_active" not in metadata:
                metadata["is_active"] = True
            mc.metadata_json = metadata  # type: ignore[assignment]

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
            "created": created,
            "skipped_bad_level": skipped_bad_level,
        }

    def _validate_unique_keys(self, rows: List[MetricRowPair]) -> None:
        seen: Dict[str, str] = {}
        dupes: Set[str] = set()
        for _, r in rows:
            norm = (r.kpi_key or "").strip().lower()
            if not norm:
                continue
            if norm in seen:
                dupes.add(seen[norm])
                dupes.add(r.kpi_key)
            else:
                seen[norm] = r.kpi_key
        if dupes:
            raise ValueError(f"Duplicate kpi_key values in Metrics_Config: {sorted(dupes)}")

    def _validate_active_north_star(self, rows: List[MetricRowPair]) -> None:
        active_ns = [r for _, r in rows if (r.kpi_level == "north_star" and (r.is_active is not False))]
        if len(active_ns) != 1:
            raise ValueError("Metrics_Config must have exactly one active north_star KPI")


__all__ = ["MetricsConfigSyncService"]
