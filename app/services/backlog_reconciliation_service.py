# productroadmap_sheet_project/app/services/backlog_reconciliation_service.py
"""Service to reconcile differences between central backlog sheet and DB records."""
from __future__ import annotations

import json
import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from app.db.models.initiative import Initiative
from app.services.backlog_field_ownership import DB_OWNED_FIELDS, EXTERNAL_OWNED_FIELDS, FIELD_TO_CENTRAL_HEADER, SHEET_OWNED_FIELDS
from app.services.backlog_mapper import FIELD_CONVERTERS
from app.sheets.backlog_reader import BacklogReader, BacklogRow
from app.sheets.backlog_writer import write_backlog_fields_batch
from app.sheets.client import SheetsClient
from app.sheets.models import CENTRAL_HEADER_TO_FIELD
from app.utils.header_utils import get_value_by_header_alias

logger = logging.getLogger(__name__)

SYNC_UPDATED_SOURCE = "pm.sync_backlog_db"
ALLOW_SHEET_CLEAR_FIELDS: frozenset[str] = frozenset()
DB_RECONCILIATION_COMMIT_ROW_CHUNK_SIZE = 200
SHEET_RECONCILIATION_WRITE_ROW_CHUNK_SIZE = 200


class BacklogReconciliationService:
    def __init__(self, sheets_client: SheetsClient) -> None:
        self.sheets_client = sheets_client

    def sync(
        self,
        *,
        db: Session,
        spreadsheet_id: str,
        tab_name: str,
        initiative_keys: list[str],
    ) -> dict[str, Any]:
        reader = BacklogReader(self.sheets_client)
        rows = reader.get_rows(spreadsheet_id=spreadsheet_id, tab_name=tab_name)
        rows_by_key = {
            str(get_value_by_header_alias(row, "Initiative Key", []) or "").strip(): row
            for _, row in rows
        }

        initiatives = db.query(Initiative).filter(Initiative.initiative_key.in_(initiative_keys)).all()
        initiatives_by_key = {str(initiative.initiative_key): initiative for initiative in initiatives}

        status_by_key: dict[str, str] = {}
        changes_log: dict[str, dict[str, list[str]]] = {}
        rows_processed = 0
        rows_updated = 0
        ok_count = 0
        skipped_count = 0
        failed_count = 0
        no_op_count = 0
        db_rows_updated = 0
        db_fields_updated = 0
        sheet_fields_updated = 0
        pending_db_rows_updated = 0
        pending_sheet_updates: dict[str, dict[str, Any]] = {}
        sheet_updated_total = 0

        for key in initiative_keys:
            row = rows_by_key.get(key)
            initiative = initiatives_by_key.get(key)

            if row is None or initiative is None:
                status_by_key[key] = "SKIPPED: missing row or DB record"
                skipped_count += 1
                continue

            try:
                with db.begin_nested():
                    db_change_fields = self._apply_sheet_to_db(row, initiative)
                    db_field_changes = len(db_change_fields)
                    if db_field_changes:
                        db.flush()
                    sheet_updates, sheet_change_fields = self._extract_db_to_sheet(row, initiative)

                rows_processed += 1
                db_fields_updated += db_field_changes
                if db_field_changes:
                    db_rows_updated += 1
                    pending_db_rows_updated += 1

                if sheet_updates:
                    pending_sheet_updates[key] = sheet_updates
                    sheet_fields_updated += len(sheet_updates)

                if db_change_fields or sheet_change_fields:
                    changes_log[key] = {
                        "db": db_change_fields,
                        "sheet": sheet_change_fields,
                    }

                if db_field_changes or sheet_change_fields:
                    rows_updated += 1
                    status_by_key[key] = "OK"
                else:
                    no_op_count += 1
                    status_by_key[key] = "OK: no changes"

                ok_count += 1

                if pending_db_rows_updated >= DB_RECONCILIATION_COMMIT_ROW_CHUNK_SIZE:
                    db.commit()
                    pending_db_rows_updated = 0

                if len(pending_sheet_updates) >= SHEET_RECONCILIATION_WRITE_ROW_CHUNK_SIZE:
                    if pending_db_rows_updated:
                        db.commit()
                        pending_db_rows_updated = 0
                    sheet_updated_total += write_backlog_fields_batch(
                        self.sheets_client,
                        spreadsheet_id,
                        tab_name,
                        updates_by_key=pending_sheet_updates,
                    )
                    pending_sheet_updates = {}
            except Exception as exc:
                logger.exception("backlog_reconciliation.row_failed", extra={"initiative_key": key})
                status_by_key[key] = f"FAILED: {str(exc)[:80]}"
                failed_count += 1

        if pending_db_rows_updated:
            db.commit()

        if pending_sheet_updates:
            sheet_updated_total += write_backlog_fields_batch(
                self.sheets_client,
                spreadsheet_id,
                tab_name,
                updates_by_key=pending_sheet_updates,
            )

        return {
            "selected_count": len(initiative_keys),
            "rows_processed": rows_processed,
            "rows_updated": rows_updated,
            "rows_skipped": skipped_count,
            "ok_count": ok_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "no_op_count": no_op_count,
            "db_updated": db_rows_updated,
            "db_rows_updated": db_rows_updated,
            "db_fields_updated": db_fields_updated,
            "sheet_updated": sheet_updated_total,
            "sheet_fields_updated": sheet_fields_updated,
            "fields_updated": db_fields_updated + sheet_fields_updated,
            "changes_log": changes_log,
            "status_by_key": status_by_key,
        }

    @staticmethod
    def _apply_sheet_to_db(row: BacklogRow, initiative: Initiative) -> list[str]:
        changed_fields: list[str] = []
        for sheet_header, field_name in CENTRAL_HEADER_TO_FIELD.items():
            if field_name not in SHEET_OWNED_FIELDS:
                continue
            if field_name in EXTERNAL_OWNED_FIELDS:
                continue
            if sheet_header not in row:
                continue
            raw_value = get_value_by_header_alias(row, sheet_header, [])
            converter = FIELD_CONVERTERS.get(field_name, lambda value: value)
            current_value = getattr(initiative, field_name, None)
            new_value = converter(raw_value)

            if BacklogReconciliationService._should_skip_empty_clear(field_name, current_value, new_value):
                continue
            if BacklogReconciliationService._values_equal(current_value, new_value):
                continue

            setattr(initiative, field_name, new_value)
            changed_fields.append(field_name)

        if changed_fields:
            cast(Any, initiative).updated_source = SYNC_UPDATED_SOURCE
        return changed_fields

    @staticmethod
    def _extract_db_to_sheet(row: BacklogRow, initiative: Initiative) -> tuple[dict[str, Any], list[str]]:
        updates: dict[str, Any] = {}
        changed_fields: list[str] = []
        for field in sorted(DB_OWNED_FIELDS):
            header = FIELD_TO_CENTRAL_HEADER.get(field)
            if not header or header not in row:
                continue
            db_value = BacklogReconciliationService._sheet_value_for_field(initiative, field)
            sheet_value = get_value_by_header_alias(row, header, [])
            if BacklogReconciliationService._values_equal(sheet_value, db_value):
                continue
            updates[field] = db_value
            changed_fields.append(field)
        return updates, changed_fields

    @staticmethod
    def _sheet_value_for_field(initiative: Initiative, field: str) -> Any:
        if field == "metric_chain_json":
            primary_model = next((model for model in initiative.math_models if model.is_primary), None)
            metric_chain = primary_model.metric_chain_json if primary_model else None
            if metric_chain in (None, ""):
                return None
            if isinstance(metric_chain, str):
                return metric_chain
            try:
                return json.dumps(metric_chain)
            except Exception:
                return str(metric_chain)
        return getattr(initiative, field, None)

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped.casefold() if stripped else None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return round(float(value), 6)
        if isinstance(value, dict):
            try:
                return json.dumps(value, sort_keys=True, ensure_ascii=True)
            except Exception:
                return str(value).strip().casefold()
        if isinstance(value, (list, tuple, set)):
            normalized_items = []
            for item in value:
                normalized_item = BacklogReconciliationService._normalize_value(item)
                if normalized_item is None:
                    continue
                normalized_items.append(normalized_item)
            return tuple(sorted(normalized_items, key=str))
        return str(value).strip().casefold()

    @staticmethod
    def _values_equal(left: Any, right: Any) -> bool:
        return BacklogReconciliationService._normalize_value(left) == BacklogReconciliationService._normalize_value(right)

    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        normalized = BacklogReconciliationService._normalize_value(value)
        if normalized is None:
            return True
        if isinstance(normalized, tuple):
            return len(normalized) == 0
        return False

    @staticmethod
    def _should_skip_empty_clear(field_name: str, current_value: Any, new_value: Any) -> bool:
        if field_name in ALLOW_SHEET_CLEAR_FIELDS:
            return False
        return BacklogReconciliationService._is_empty_value(new_value) and not BacklogReconciliationService._is_empty_value(current_value)


__all__ = ["BacklogReconciliationService"]