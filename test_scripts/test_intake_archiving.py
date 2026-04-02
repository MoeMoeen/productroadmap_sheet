from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.initiative import Initiative
from app.jobs.sync_intake_job import reconcile_intake_managed_initiatives
from app.services.intake_service import IntakeService
from app.sheets.backlog_writer import write_backlog_from_db


class FakeSheetsClient:
    def __init__(self, header: list[str]) -> None:
        self.header = header
        self.cleared_ranges: list[str] = []
        self.updated_batches: list[list[dict]] = []

    def get_values(self, spreadsheet_id: str, range_: str, value_render_option: str = "UNFORMATTED_VALUE"):
        return [self.header]

    def get_sheet_grid_size(self, spreadsheet_id: str, tab_name: str) -> tuple[int, int]:
        return (50, len(self.header))

    def clear_values(self, spreadsheet_id: str, range_: str) -> None:
        self.cleared_ranges.append(range_)

    def batch_update_values(self, spreadsheet_id: str, data: list[dict], value_input_option: str = "USER_ENTERED") -> None:
        self.updated_batches.append(data)

    def get_sheet_properties(self, spreadsheet_id: str, tab_name: str) -> dict:
        return {}

    def batch_update(self, spreadsheet_id: str, requests: list[dict]) -> None:
        return None


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_initiative(
    db_session,
    *,
    initiative_key: str,
    title: str = "Test Initiative",
    source_sheet_id: str | None = None,
    source_tab_name: str | None = None,
    source_row_number: int | None = None,
    is_archived: bool = False,
    archived_reason: str | None = None,
    archived_at: datetime | None = None,
    is_optimization_candidate: bool = False,
    candidate_period_key: str | None = None,
) -> Initiative:
    initiative = Initiative(
        initiative_key=initiative_key,
        title=title,
        source_sheet_id=source_sheet_id,
        source_tab_name=source_tab_name,
        source_row_number=source_row_number,
        is_archived=is_archived,
        archived_reason=archived_reason,
        archived_at=archived_at,
        is_optimization_candidate=is_optimization_candidate,
        candidate_period_key=candidate_period_key,
    )
    db_session.add(initiative)
    db_session.commit()
    db_session.refresh(initiative)
    return initiative


def test_new_intake_initiative_created_and_active(db_session) -> None:
    service = IntakeService(db_session)

    initiative, was_created = service.upsert_from_intake_row_with_status(
        row={"Title": "New Initiative", "Department": "Marketing", "Requesting Team": "Growth"},
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=2,
        auto_commit=False,
    )
    db_session.commit()
    db_session.refresh(initiative)

    assert was_created is True
    assert getattr(initiative, "title", None) == "New Initiative"
    assert bool(getattr(initiative, "is_archived", False)) is False


def test_existing_intake_initiative_remains_active_after_reconcile(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000001",
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=2,
    )

    stats = reconcile_intake_managed_initiatives(
        db_session,
        {"INIT-000001"},
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)

    assert bool(getattr(initiative, "is_archived", False)) is False
    assert stats["archived_count"] == 0
    assert stats["unarchived_count"] == 0


def test_missing_intake_initiative_is_soft_archived(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000002",
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=3,
    )

    stats = reconcile_intake_managed_initiatives(
        db_session,
        set(),
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)

    assert bool(getattr(initiative, "is_archived", False)) is True
    assert getattr(initiative, "archived_reason", None) == "missing_from_intake_sync"
    assert getattr(initiative, "archived_at", None) is not None
    assert stats["archived_count"] == 1


def test_archived_initiative_reappearing_is_unarchived(db_session) -> None:
    archived_at = datetime.now(timezone.utc)
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000003",
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=4,
        is_archived=True,
        archived_reason="missing_from_intake_sync",
        archived_at=archived_at,
    )

    service = IntakeService(db_session)
    service.upsert_from_intake_row_with_status(
        row={"Initiative Key": "INIT-000003", "Title": "Restored Initiative"},
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=10,
        auto_commit=False,
    )
    db_session.commit()

    stats = reconcile_intake_managed_initiatives(
        db_session,
        {"INIT-000003"},
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)

    assert getattr(initiative, "title", None) == "Restored Initiative"
    assert bool(getattr(initiative, "is_archived", False)) is False
    assert getattr(initiative, "archived_at", None) is None
    assert getattr(initiative, "archived_reason", None) is None
    assert stats["unarchived_count"] == 1


def test_non_intake_initiative_not_archived(db_session) -> None:
    initiative = _create_initiative(db_session, initiative_key="INIT-000004")

    stats = reconcile_intake_managed_initiatives(
        db_session,
        set(),
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)

    assert bool(getattr(initiative, "is_archived", False)) is False
    assert stats["db_intake_managed_checked"] == 0


def test_pm_owned_fields_preserved_for_surviving_initiative(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000005",
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=5,
        is_optimization_candidate=True,
        candidate_period_key="2026-Q2",
    )
    service = IntakeService(db_session)

    service.upsert_from_intake_row_with_status(
        row={"Initiative Key": "INIT-000005", "Title": "Updated Intake Title", "Department": "Marketing"},
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=5,
        auto_commit=False,
    )
    db_session.commit()
    db_session.refresh(initiative)

    assert getattr(initiative, "title", None) == "Updated Intake Title"
    assert bool(getattr(initiative, "is_optimization_candidate", False)) is True
    assert getattr(initiative, "candidate_period_key", None) == "2026-Q2"


def test_backlog_writer_excludes_archived_by_default(db_session) -> None:
    _create_initiative(db_session, initiative_key="INIT-000006", title="Visible")
    _create_initiative(
        db_session,
        initiative_key="INIT-000007",
        title="Archived",
        is_archived=True,
        archived_reason="missing_from_intake_sync",
        archived_at=datetime.now(timezone.utc),
    )
    client = FakeSheetsClient(["Initiative Key", "Title"])

    result = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
    )

    assert result["initiatives_written"] == 1
    assert result["archived_rows_excluded"] == 1

    result_with_archived = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
        include_archived=True,
    )
    assert result_with_archived["initiatives_written"] == 2
    assert result_with_archived["archived_rows_excluded"] == 0


def test_backlog_writer_renders_archive_columns_when_present(db_session) -> None:
    archived_at = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    _create_initiative(
        db_session,
        initiative_key="INIT-000009",
        title="Archived Visible",
        is_archived=True,
        archived_reason="missing_from_intake_sync",
        archived_at=archived_at,
    )
    client = FakeSheetsClient(["Initiative Key", "Title", "Is Archived", "Archived At", "Archived Reason"])

    result = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
        include_archived=True,
    )

    assert result["initiatives_written"] == 1

    flat_updates = {
        item["range"]: item["values"][0][0]
        for batch in client.updated_batches
        for item in batch
    }
    assert flat_updates["Backlog!A5"] == "INIT-000009"
    assert flat_updates["Backlog!B5"] == "Archived Visible"
    assert flat_updates["Backlog!C5"] is True
    assert str(flat_updates["Backlog!D5"]).startswith("2026-04-02T12:00:00")
    assert flat_updates["Backlog!E5"] == "missing_from_intake_sync"


def test_reconcile_is_idempotent(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000008",
        source_sheet_id="sheet-1",
        source_tab_name="Marketing_EMEA",
        source_row_number=6,
    )

    first = reconcile_intake_managed_initiatives(
        db_session,
        set(),
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)
    archived_at = getattr(initiative, "archived_at", None)

    second = reconcile_intake_managed_initiatives(
        db_session,
        set(),
        managed_scopes=[("sheet-1", "Marketing_EMEA")],
    )
    db_session.refresh(initiative)

    assert first["archived_count"] == 1
    assert second["archived_count"] == 0
    assert second["already_archived_count"] == 1
    assert bool(getattr(initiative, "is_archived", False)) is True
    assert getattr(initiative, "archived_at", None) == archived_at