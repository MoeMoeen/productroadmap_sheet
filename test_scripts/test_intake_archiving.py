from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.initiative import Initiative
from app.jobs.flow3_product_ops_job import run_flow3_sync_inputs_to_initiatives
from app.jobs.flow3_product_ops_job import run_flow3_populate_initiatives
from app.jobs.sync_intake_job import reconcile_intake_managed_initiatives
from app.jobs.sync_intake_job import run_sync_for_sheet
from app.jobs.sync_intake_job import run_sync_all_intake_sheets
from app.services.action_runner import ActionContext, _action_pm_backlog_sync, _action_pm_populate_candidates, _action_pm_populate_initiatives, _action_pm_save_selected, _action_pm_score_selected, _action_pm_seed_math_params, _action_pm_suggest_math_model_llm, _action_pm_switch_framework, _extract_summary
from app.services.intake_mapper import map_sheet_row_to_initiative_create
from app.services.intake_service import IntakeService
from app.sheets.backlog_writer import write_backlog_from_db
from app.sheets.intake_writer import GoogleSheetsIntakeWriter
from app.sheets.layout import data_start_row
from app.sheets.productops_writer import upsert_initiatives_to_scoring_inputs
from app.sheets.scoring_inputs_reader import ScoringInputsRow
from app.config import BacklogSheetConfig, IntakeSheetConfig, IntakeTabConfig, settings


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

    def batch_clear_values(self, spreadsheet_id: str, ranges: list[str]) -> None:
        self.cleared_ranges.extend(ranges)

    def batch_update_values(self, spreadsheet_id: str, data: list[dict], value_input_option: str = "USER_ENTERED") -> None:
        self.updated_batches.append(data)

    def get_sheet_properties(self, spreadsheet_id: str, tab_name: str) -> dict:
        return {}

    def batch_update(self, spreadsheet_id: str, requests: list[dict]) -> None:
        return None


class CountingSheetsClient(FakeSheetsClient):
    def __init__(self, header: list[str]) -> None:
        super().__init__(header)
        self.get_values_calls = 0

    def get_values(self, spreadsheet_id: str, range_: str, value_render_option: str = "UNFORMATTED_VALUE"):
        self.get_values_calls += 1
        return super().get_values(spreadsheet_id, range_, value_render_option)


class PopulateScoringInputsClient:
    def __init__(self, header: list[str], values_by_range: dict[str, list[list[Any]]]) -> None:
        self.header = header
        self.values_by_range = values_by_range
        self.updated: list[dict[str, Any]] = []

    def get_values(self, spreadsheet_id: str, range_: str, value_render_option: str = "UNFORMATTED_VALUE"):
        if range_.endswith("!1:1"):
            return [self.header]
        return self.values_by_range.get(range_, [])

    def batch_get_values(self, spreadsheet_id: str, ranges: list[str], value_render_option: str = "UNFORMATTED_VALUE") -> list[dict[str, Any]]:
        return [{"values": self.values_by_range.get(range_, [])} for range_ in ranges]

    def batch_update_values(self, spreadsheet_id: str, data: list[dict], value_input_option: str = "USER_ENTERED") -> None:
        self.updated.extend(data)


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
    source_sheet_key: str | None = None,
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
        source_sheet_key=source_sheet_key,
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
        source_sheet_key="emea_intake",
        source_tab_name="Marketing_EMEA",
        source_row_number=2,
        auto_commit=False,
    )
    db_session.commit()
    db_session.refresh(initiative)

    assert was_created is True
    assert getattr(initiative, "title", None) == "New Initiative"
    assert bool(getattr(initiative, "is_archived", False)) is False
    assert getattr(initiative, "source_sheet_key", None) == "emea_intake"


def test_intake_mapper_only_reads_intake_fields() -> None:
    dto = map_sheet_row_to_initiative_create(
        {
            "Title": "New Initiative",
            "Department": "Marketing",
            "Requesting Team": "Growth",
            "Problem Statement": "Customer drop-off is high",
            "Deadline Date": "2026-04-30",
            "Lifecycle Status": "new",
            "Market": "MENA",
            "Category": "Growth",
            "Hypothesis": "Should be ignored",
            "Customer Segment": "SMB",
            "Initiative Type": "Feature",
            "Effort T-shirt Size": "M",
            "Effort Engineering Days": "10",
            "Effort Other Teams Days": "4",
            "Infra Cost Estimate": "500",
            "Engineering Tokens": "250",
            "Dependencies Others": "Legal",
            "Program Key": "program-alpha",
            "Risk Level": "high",
            "Risk Description": "Needs migration",
            "Time Sensitivity": "4.5",
        }
    )

    dumped = dto.model_dump()

    assert dumped["department"] == "Marketing"
    assert dumped["requesting_team"] == "Growth"
    assert dumped["problem_statement"] == "Customer drop-off is high"
    assert str(dumped["deadline_date"]) == "2026-04-30"
    assert dumped["lifecycle_status"] == "new"
    assert dumped["market"] is None
    assert dumped["category"] is None
    assert dumped["hypothesis"] is None
    assert dumped["customer_segment"] is None
    assert dumped["initiative_type"] is None
    assert dumped["effort_tshirt_size"] is None
    assert dumped["effort_engineering_days"] is None
    assert dumped["effort_other_teams_days"] is None
    assert dumped["infra_cost_estimate"] is None
    assert dumped["engineering_tokens"] is None
    assert dumped["dependencies_others"] is None
    assert dumped["program_key"] is None
    assert dumped["risk_level"] is None
    assert dumped["risk_description"] is None
    assert dumped["time_sensitivity_score"] is None


def test_intake_mapper_resolves_header_aliases() -> None:
    dto = map_sheet_row_to_initiative_create(
        {
            "title": "Alias Initiative",
            "dept": "Leadership",
            "requesting_team": "PMO",
            "problem_statement": "Need header normalization",
			"deadline_date": "2026-05-15",
            "status": "new",
        }
    )

    dumped = dto.model_dump()

    assert dumped["title"] == "Alias Initiative"
    assert dumped["department"] == "Leadership"
    assert dumped["requesting_team"] == "PMO"
    assert dumped["problem_statement"] == "Need header normalization"
    assert str(dumped["deadline_date"]) == "2026-05-15"
    assert dumped["lifecycle_status"] == "new"


def test_existing_intake_initiative_remains_active_after_reconcile(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000001",
        source_sheet_id="sheet-1",
        source_sheet_key="emea_intake",
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


def test_intake_service_blocks_withdrawn_to_new_without_override(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000001A",
        source_sheet_id="sheet-1",
        source_sheet_key="emea_intake",
        source_tab_name="Marketing_EMEA",
        source_row_number=22,
    )
    setattr(initiative, "lifecycle_status", "withdrawn")
    db_session.commit()

    service = IntakeService(db_session)
    service.upsert_from_intake_row_with_status(
        row={"Initiative Key": "INIT-000001A", "Title": "Still Withdrawn", "Lifecycle Status": "new"},
        source_sheet_id="sheet-1",
        source_sheet_key="emea_intake",
        source_tab_name="Marketing_EMEA",
        source_row_number=22,
        auto_commit=False,
    )
    db_session.commit()
    db_session.refresh(initiative)

    assert getattr(initiative, "title", None) == "Still Withdrawn"
    assert getattr(initiative, "lifecycle_status", None) == "withdrawn"


def test_missing_intake_initiative_is_soft_archived(db_session) -> None:
    initiative = _create_initiative(
        db_session,
        initiative_key="INIT-000002",
        source_sheet_id="sheet-1",
        source_sheet_key="emea_intake",
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
        source_sheet_key="emea_intake",
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
        source_sheet_key="emea_intake",
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
        source_sheet_key="emea_intake",
        source_tab_name="Marketing_EMEA",
        source_row_number=5,
        is_optimization_candidate=True,
        candidate_period_key="2026-Q2",
    )
    service = IntakeService(db_session)

    service.upsert_from_intake_row_with_status(
        row={"Initiative Key": "INIT-000005", "Title": "Updated Intake Title", "Department": "Marketing"},
        source_sheet_id="sheet-1",
        source_sheet_key="emea_intake",
        source_tab_name="Marketing_EMEA",
        source_row_number=5,
        auto_commit=False,
    )
    db_session.commit()
    db_session.refresh(initiative)

    assert getattr(initiative, "title", None) == "Updated Intake Title"
    assert bool(getattr(initiative, "is_optimization_candidate", False)) is True
    assert getattr(initiative, "candidate_period_key", None) == "2026-Q2"


def test_backlog_writer_includes_archived_by_default(db_session) -> None:
    _create_initiative(db_session, initiative_key="INIT-000006", title="Visible")
    _create_initiative(
        db_session,
        initiative_key="INIT-000007",
        title="Populate Title",
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

    assert result["initiatives_written"] == 2
    assert result["archived_rows_excluded"] == 0

    result_without_archived = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
        include_archived=False,
    )
    assert result_without_archived["initiatives_written"] == 1
    assert result_without_archived["archived_rows_excluded"] == 1


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


def test_backlog_writer_renders_intake_source_column(db_session) -> None:
    _create_initiative(
        db_session,
        initiative_key="INIT-000015",
        title="Visible",
        source_sheet_key="mena_intake",
        source_tab_name="UAE",
    )
    client = FakeSheetsClient(["Initiative Key", "Title", "Intake Source"])

    result = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
    )

    assert result["initiatives_written"] == 1

    flat_updates = {
        item["range"]: item["values"][0][0]
        for batch in client.updated_batches
        for item in batch
    }
    assert flat_updates["Backlog!C5"] == "mena_intake / UAE"


def test_backlog_writer_derives_missing_sheet_key_for_intake_source(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_sheets = list(settings.INTAKE_SHEETS)
    settings.INTAKE_SHEETS = [
        IntakeSheetConfig(
            sheet_key="intake_emea",
            spreadsheet_id="sheet-1",
            tabs=[
                IntakeTabConfig(
                    key="marketing_emea",
                    spreadsheet_id="sheet-1",
                    tab_name="Marketing_EMEA",
                )
            ],
        )
    ]
    try:
        _create_initiative(
            db_session,
            initiative_key="INIT-000016",
            title="Derived Source",
            source_sheet_id="sheet-1",
            source_tab_name="Marketing_EMEA",
        )
        client = FakeSheetsClient(["Initiative Key", "Title", "Intake Source"])

        write_backlog_from_db(
            db_session,
            cast(Any, client),
            backlog_spreadsheet_id="spreadsheet-1",
            backlog_tab_name="Backlog",
        )

        flat_updates = {
            item["range"]: item["values"][0][0]
            for batch in client.updated_batches
            for item in batch
        }
        assert flat_updates["Backlog!C5"] == "intake_emea / Marketing_EMEA"
    finally:
        settings.INTAKE_SHEETS = original_sheets


def test_reconcile_backfills_missing_source_sheet_key_from_config(db_session) -> None:
    original_sheets = list(settings.INTAKE_SHEETS)
    settings.INTAKE_SHEETS = [
        IntakeSheetConfig(
            sheet_key="intake_emea",
            spreadsheet_id="sheet-1",
            tabs=[
                IntakeTabConfig(
                    key="marketing_emea",
                    spreadsheet_id="sheet-1",
                    tab_name="Marketing_EMEA",
                )
            ],
        )
    ]
    try:
        initiative = _create_initiative(
            db_session,
            initiative_key="INIT-000017",
            title="Needs Provenance",
            source_sheet_id="sheet-1",
            source_tab_name="Marketing_EMEA",
        )

        result = reconcile_intake_managed_initiatives(db_session, {"INIT-000017"})
        db_session.refresh(initiative)

        assert result["provenance_backfilled_count"] == 1
        assert getattr(initiative, "source_sheet_key", None) == "intake_emea"
        assert getattr(initiative, "is_archived", False) is False
    finally:
        settings.INTAKE_SHEETS = original_sheets


def test_backlog_writer_preserves_non_owned_columns(db_session) -> None:
    _create_initiative(db_session, initiative_key="INIT-000010", title="Visible")
    client = FakeSheetsClient(["Initiative Key", "Title", "PM Helper Formula"])

    result = write_backlog_from_db(
        db_session,
        cast(Any, client),
        backlog_spreadsheet_id="spreadsheet-1",
        backlog_tab_name="Backlog",
    )

    dsr = data_start_row("Backlog")
    assert result["initiatives_written"] == 1
    assert client.cleared_ranges == [
        f"Backlog!A{dsr}:A50",
        f"Backlog!B{dsr}:B50",
    ]
    assert all("C" not in clear_range for clear_range in client.cleared_ranges)


def test_flow3_populate_excludes_archived_candidates(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_initiative(
        db_session,
        initiative_key="INIT-000011",
        title="Populate Title",
        is_optimization_candidate=True,
        is_archived=False,
    )
    _create_initiative(
        db_session,
        initiative_key="INIT-000012",
        is_optimization_candidate=True,
        is_archived=True,
    )

    class FakeScoringInputsReader:
        def __init__(self, client: Any, spreadsheet_id: str, tab_name: str) -> None:
            self.client = client
            self.spreadsheet_id = spreadsheet_id
            self.tab_name = tab_name

        def read(self) -> list[Any]:
            return []

    captured_initiatives: list[dict[str, str]] = []

    def fake_upsert_initiatives_to_scoring_inputs(*, client: Any, spreadsheet_id: str, tab_name: str, initiatives: list[dict[str, str]]) -> dict[str, int]:
        captured_initiatives.extend(initiatives)
        return {"appended": len(initiatives), "titles_backfilled": 0}

    monkeypatch.setattr(
        "app.jobs.flow3_product_ops_job.ScoringInputsReader",
        FakeScoringInputsReader,
    )
    monkeypatch.setattr(
        "app.sheets.productops_writer.upsert_initiatives_to_scoring_inputs",
        fake_upsert_initiatives_to_scoring_inputs,
    )

    result = run_flow3_populate_initiatives(
        db_session,
        client=cast(Any, object()),
        spreadsheet_id="spreadsheet-1",
        tab_name="Scoring_Inputs",
    )

    assert result["total_candidates"] == 1
    assert result["newly_added"] == 1
    assert result["titles_backfilled"] == 0
    assert captured_initiatives == [{"initiative_key": "INIT-000011", "title": "Populate Title"}]


def test_flow3_populate_returns_consistent_empty_shape(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeScoringInputsReader:
        def __init__(self, client: Any, spreadsheet_id: str, tab_name: str) -> None:
            raise AssertionError("reader should not be constructed when there are no candidates")

    monkeypatch.setattr(
        "app.jobs.flow3_product_ops_job.ScoringInputsReader",
        FakeScoringInputsReader,
    )

    result = run_flow3_populate_initiatives(
        db_session,
        client=cast(Any, object()),
        spreadsheet_id="spreadsheet-1",
        tab_name="Scoring_Inputs",
    )

    assert result == {
        "total_candidates": 0,
        "existing_in_sheet": 0,
        "newly_added": 0,
        "titles_backfilled": 0,
        "db_collisions": 0,
        "sheet_collisions": 0,
    }


def test_upsert_initiatives_to_scoring_inputs_matches_headers_and_backfills_empty_titles() -> None:
    client = PopulateScoringInputsClient(
        ["Notes", "Initiative Title", "Initiative Key"],
        {
            "Scoring_Inputs!C5:C": [["INIT-000001"]],
            "Scoring_Inputs!B5:B": [[""]],
        },
    )

    result = upsert_initiatives_to_scoring_inputs(
        client=cast(Any, client),
        spreadsheet_id="spreadsheet-1",
        tab_name="Scoring_Inputs",
        initiatives=[
            {"initiative_key": "INIT-000001", "title": "Existing Title"},
            {"initiative_key": "INIT-000002", "title": "New Title"},
        ],
    )

    assert result == {"appended": 1, "titles_backfilled": 1}
    assert client.updated == [
        {"range": "Scoring_Inputs!B5", "values": [["Existing Title"]]},
        {"range": "Scoring_Inputs!C6", "values": [["INIT-000002"]]},
        {"range": "Scoring_Inputs!B6", "values": [["New Title"]]},
    ]


def test_upsert_initiatives_to_scoring_inputs_warns_when_title_column_missing(caplog: pytest.LogCaptureFixture) -> None:
    client = PopulateScoringInputsClient(
        ["Notes", "Title", "Initiative Key"],
        {
            "Scoring_Inputs!C5:C": [],
        },
    )

    with caplog.at_level("WARNING"):
        result = upsert_initiatives_to_scoring_inputs(
            client=cast(Any, client),
            spreadsheet_id="spreadsheet-1",
            tab_name="Scoring_Inputs",
            initiatives=[
                {"initiative_key": "INIT-000002", "title": "New Title"},
            ],
        )

    assert result == {"appended": 1, "titles_backfilled": 0}
    assert client.updated == [
        {"range": "Scoring_Inputs!C5", "values": [["INIT-000002"]]},
    ]
    assert any(record.message == "productops_writer.upsert.title_column_missing" for record in caplog.records)


def test_run_sync_for_sheet_raises_on_backfill_failure(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.jobs.sync_intake_job.IntakeReader.get_rows_for_sheet",
        lambda self, spreadsheet_id, tab_name, header_row=1, start_data_row=2, max_rows=None: [
            (2, {"Title": "New Initiative", "Department": "Marketing", "Requesting Team": "Growth"})
        ],
    )

    def fail_backfill(self, sheet_id: str, tab_name: str, row_number: int, initiative_key: str) -> None:
        raise RuntimeError("sheet write failed")

    monkeypatch.setattr(
        "app.sheets.intake_writer.GoogleSheetsIntakeWriter.write_initiative_key",
        fail_backfill,
    )

    with pytest.raises(RuntimeError, match="sheet write failed"):
        run_sync_for_sheet(
            db_session,
            spreadsheet_id="sheet-1",
            source_sheet_key="emea_intake",
            tab_name="Marketing_EMEA",
            sheets_service=object(),
        )


def test_intake_key_writer_caches_header_reads_across_multiple_backfills() -> None:
    client = CountingSheetsClient(["Title", "Initiative Key", "Updated At"])
    writer = GoogleSheetsIntakeWriter(cast(Any, client))

    writer.write_initiative_key("sheet-1", "Simulated_Department", 2, "INIT-000001")
    writer.write_initiative_key("sheet-1", "Simulated_Department", 3, "INIT-000002")

    assert client.get_values_calls == 1
    assert len(client.updated_batches) == 2


def test_run_sync_all_intake_sheets_reloads_runtime_tab_config(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_sheets = list(settings.INTAKE_SHEETS)
    reloaded_sheets = [
        IntakeSheetConfig(
            sheet_key="intake_emea",
            spreadsheet_id="sheet-1",
            region="EMEA",
            tabs=[
                IntakeTabConfig(
                    key="marketing_emea",
                    spreadsheet_id="sheet-1",
                    tab_name="Marketing_EMEA",
                ),
                IntakeTabConfig(
                    key="sales_emea",
                    spreadsheet_id="sheet-1",
                    tab_name="sales EMEA",
                ),
            ],
        )
    ]

    monkeypatch.setattr("app.jobs.sync_intake_job.get_sheets_service", lambda: object())
    monkeypatch.setattr(
        settings.__class__,
        "reload_intake_sheets_from_file",
        lambda self: setattr(self, "INTAKE_SHEETS", reloaded_sheets),
    )

    synced_tabs: list[str] = []

    def fake_run_sync_for_sheet(
        db,
        spreadsheet_id,
        source_sheet_key,
        tab_name,
        sheets_service=None,
        allow_status_override=False,
        header_row=1,
        start_data_row=2,
        max_rows=None,
        seen_keys=None,
        commit_every=None,
    ):
        synced_tabs.append(tab_name)
        return {
            "rows_processed": 1,
            "initiatives_created": 0,
            "initiatives_updated": 1,
            "keys_backfilled": 0,
        }

    monkeypatch.setattr("app.jobs.sync_intake_job.run_sync_for_sheet", fake_run_sync_for_sheet)
    monkeypatch.setattr(
        "app.jobs.sync_intake_job.reconcile_intake_managed_initiatives",
        lambda db, current_intake_keys, managed_scopes=None: {
            "intake_keys_seen": len(current_intake_keys),
            "db_intake_managed_checked": 0,
            "archived_count": 0,
            "already_archived_count": 0,
            "unarchived_count": 0,
        },
    )

    try:
        result = run_sync_all_intake_sheets(db_session)
    finally:
        settings.INTAKE_SHEETS = original_sheets

    assert synced_tabs == ["Marketing_EMEA", "sales EMEA"]
    assert result["sheets_processed"] == 2


def test_pm_backlog_sync_skips_backlog_update_stage(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    backlog_call: dict[str, bool] = {}

    monkeypatch.setattr(
        "app.services.action_runner.run_sync_all_intake_sheets",
        lambda db, allow_status_override_global=False, archive_missing=True: {
            "sheets_processed": 2,
            "rows_processed": 19,
            "initiatives_created": 1,
            "initiatives_updated": 18,
            "initiatives_archived": 0,
            "initiatives_unarchived": 0,
            "already_archived": 1,
            "db_intake_managed_checked": 20,
            "intake_keys_seen": 19,
            "keys_backfilled": 1,
        },
    )

    def fake_run_all_backlog_sync(db, include_archived=True):
        backlog_call["include_archived"] = include_archived
        return {
            "initiatives_written": 19,
            "cells_updated": 589,
            "archived_rows_excluded": 1,
        }

    monkeypatch.setattr(
        "app.services.action_runner.run_all_backlog_sync",
        fake_run_all_backlog_sync,
    )

    def fail_backlog_update(*args, **kwargs):
        raise AssertionError("pm.backlog_sync must not call backlog update")

    monkeypatch.setattr("app.services.action_runner.run_backlog_update", fail_backlog_update)

    ctx = ActionContext(payload={"action": "pm.backlog_sync", "options": {}}, sheets_client=cast(Any, object()), llm_client=None)

    result = _action_pm_backlog_sync(db_session, ctx)

    assert result["pm_job"] == "pm.backlog_sync"
    assert result["backlog_update_skipped"] is True
    assert result["backlog_update_completed"] is False
    assert result["substeps"] == ["flow0.intake_sync", "flow1.backlogsheet_write"]
    assert result["updated_count"] == 19
    assert result["initiatives_written"] == 19
    assert result["cells_updated"] == 589
    assert backlog_call["include_archived"] is True


def test_pm_populate_initiatives_guides_user_on_wrong_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(
        Any,
        type(
            "Cfg",
            (),
            {
                "spreadsheet_id": "sheet-1",
                "scoring_inputs_tab": "Scoring_Inputs",
                "mathmodels_tab": "MathModels",
                "params_tab": "Params",
                "metrics_config_tab": "Metrics_Config",
                "kpi_contributions_tab": "KPI_Contributions",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.action_runner.run_backlog_update",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong-tab populate must not pre-sync backlog")),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.populate_initiatives",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "KPI_Contributions"},
                "options": {"auto_sync_backlog_first": True},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )

        result = _action_pm_populate_initiatives(db_session, ctx)
        summary = _extract_summary("pm.populate_initiatives", result)

        assert result["status"] == "skipped"
        assert result["reason"] == "wrong_tab"
        assert result["target_tab"] == "Scoring_Inputs"
        assert "Go to 'Scoring_Inputs' and try again" in result["message"]
        assert "Save selected rows' in Central Backlog first" in result["backlog_save_hint"]
        assert result["backlog_presync_requested"] is True
        assert result["backlog_presync_updated"] == 0
        assert summary["success"] == 0
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_populate_initiatives_returns_counts_for_ui(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(
        Any,
        type(
            "Cfg",
            (),
            {
                "spreadsheet_id": "sheet-1",
                "scoring_inputs_tab": "Scoring_Inputs",
                "mathmodels_tab": "MathModels",
                "params_tab": "Params",
                "metrics_config_tab": "Metrics_Config",
                "kpi_contributions_tab": "KPI_Contributions",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_populate_initiatives",
        lambda db, client, spreadsheet_id, tab_name: {
            "total_candidates": 10,
            "existing_in_sheet": 0,
            "newly_added": 10,
            "titles_backfilled": 3,
            "db_collisions": 0,
            "sheet_collisions": 0,
        },
    )

    try:
        ctx = ActionContext(
            payload={
                "action": "pm.populate_initiatives",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Scoring_Inputs"},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )

        result = _action_pm_populate_initiatives(db_session, ctx)
        summary = _extract_summary("pm.populate_initiatives", result)

        assert result["status"] == "ok"
        assert result["newly_added"] == 10
        assert result["existing_in_sheet"] == 0
        assert result["titles_backfilled"] == 3
        assert summary["total"] == 10
        assert summary["success"] == 10
        assert summary["skipped"] == 0
        assert summary["titles_backfilled"] == 3
        assert "reads DB state only" in result["backlog_save_hint"]
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_populate_initiatives_can_presync_backlog_before_populating(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "scoring_inputs_tab": "Scoring_Inputs"})())
    calls: dict[str, Any] = {}

    def fake_backlog_update(db, spreadsheet_id=None, tab_name=None, product_org=None, commit_every=None, initiative_keys=None):
        calls["product_org"] = product_org
        return 7

    monkeypatch.setattr("app.services.action_runner.run_backlog_update", fake_backlog_update)
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_populate_initiatives",
        lambda db, client, spreadsheet_id, tab_name: {
            "total_candidates": 10,
            "existing_in_sheet": 2,
            "newly_added": 8,
            "titles_backfilled": 4,
            "db_collisions": 0,
            "sheet_collisions": 0,
        },
    )

    try:
        ctx = ActionContext(
            payload={
                "action": "pm.populate_initiatives",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Scoring_Inputs"},
                "options": {"auto_sync_backlog_first": True, "product_org": "Core"},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )

        result = _action_pm_populate_initiatives(db_session, ctx)

        assert calls["product_org"] == "Core"
        assert result["backlog_presync_requested"] is True
        assert result["backlog_presync_updated"] == 7
        assert result["newly_added"] == 8
        assert result["titles_backfilled"] == 4
        assert result["substeps"][0] == {"step": "backlog_presync", "status": "ok", "count": 7}
        assert result["substeps"][1] == {"step": "populate_from_db", "status": "ok", "count": 8}
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_score_selected_guides_user_on_wrong_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "scoring_inputs_tab": "Scoring_Inputs"})())
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_sync_inputs_to_initiatives",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong-tab score_selected must not sync inputs")),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.score_selected",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "KPI_Contributions"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_score_selected(db_session, ctx)
        summary = _extract_summary("pm.score_selected", result)
        assert result["status"] == "skipped"
        assert result["reason"] == "wrong_tab"
        assert result["target_tab"] == "Scoring_Inputs"
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_switch_framework_guides_user_on_wrong_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "scoring_inputs_tab": "Scoring_Inputs"})())
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_sync_inputs_to_initiatives",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong-tab switch_framework must not sync inputs")),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.switch_framework",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "MathModels"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_switch_framework(db_session, ctx)
        summary = _extract_summary("pm.switch_framework", result)
        assert result["status"] == "skipped"
        assert result["reason"] == "wrong_tab"
        assert result["target_tabs"] == ["Scoring_Inputs", "Backlog"]
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_save_selected_guides_user_on_unsupported_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(
        Any,
        type(
            "Cfg",
            (),
            {
                "spreadsheet_id": "sheet-1",
                "scoring_inputs_tab": "Scoring_Inputs",
                "mathmodels_tab": "MathModels",
                "params_tab": "Params",
                "metrics_config_tab": "Metrics_Config",
                "kpi_contributions_tab": "KPI_Contributions",
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_sync_inputs_to_initiatives",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unsupported-tab save_selected must not sync inputs")),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.save_selected",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Config"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_save_selected(db_session, ctx)
        summary = _extract_summary("pm.save_selected", result)
        assert result["status"] == "skipped"
        assert result["reason"] == "wrong_tab"
        assert "does not support 'Config'" in result["message"]
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_suggest_math_model_guides_user_on_wrong_tab(db_session) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "mathmodels_tab": "MathModels"})())
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.suggest_math_model_llm",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Scoring_Inputs"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_suggest_math_model_llm(db_session, ctx)
        summary = _extract_summary("pm.suggest_math_model_llm", result)
        assert result["status"] == "skipped"
        assert result["target_tab"] == "MathModels"
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_seed_math_params_guides_user_on_wrong_tab(db_session) -> None:
    original_product_ops = settings.PRODUCT_OPS
    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "mathmodels_tab": "MathModels", "params_tab": "Params"})())
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.seed_math_params",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Params"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_seed_math_params(db_session, ctx)
        summary = _extract_summary("pm.seed_math_params", result)
        assert result["status"] == "skipped"
        assert result["target_tab"] == "MathModels"
        assert summary["skipped"] == 1
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_save_selected_routes_normalized_mathmodels_tab_to_canonical_branch(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    status_writes: list[tuple[str, str]] = []
    service_calls: list[str] = []

    class FakeMathModelSyncService:
        def __init__(self, sheets_client: Any) -> None:
            self.sheets_client = sheets_client

        def sync_sheet_to_db(self, *, db: Any, spreadsheet_id: str, tab_name: str, commit_every: int, initiative_keys: list[str]) -> dict[str, int]:
            service_calls.append(tab_name)
            return {"updated": len(initiative_keys)}

    monkeypatch.setattr("app.services.action_runner.MathModelSyncService", FakeMathModelSyncService)
    monkeypatch.setattr(
        "app.sheets.productops_writer.write_status_to_productops_sheet",
        lambda _client, _spreadsheet_id, tab_name, _statuses: status_writes.append(("status", tab_name)),
    )

    settings.PRODUCT_OPS = cast(
        Any,
        type(
            "Cfg",
            (),
            {
                "spreadsheet_id": "sheet-1",
                "scoring_inputs_tab": "Scoring_Inputs",
                "mathmodels_tab": "MathModels",
                "params_tab": "Params",
                "metrics_config_tab": "Metrics_Config",
                "kpi_contributions_tab": "KPI_Contributions",
            },
        )(),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.save_selected",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "math models"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_save_selected(db_session, ctx)
        assert result["tab"] == "MathModels"
        assert service_calls == ["MathModels"]
        assert status_writes == [("status", "MathModels")]
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_switch_framework_routes_normalized_scoring_tab_to_canonical_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    sync_tabs: list[str] = []
    write_tabs: list[str] = []
    status_tabs: list[str] = []

    class FakeScoringService:
        latest_math_warnings = None

        def __init__(self, db: Any) -> None:
            self.db = db

        def activate_for_initiatives(self, keys: list[str], commit_every: int) -> int:
            return len(keys)

    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_sync_inputs_to_initiatives",
        lambda **kwargs: sync_tabs.append(kwargs["tab_name"]) or len(kwargs["initiative_keys"]),
    )
    monkeypatch.setattr("app.services.action_runner.ScoringService", FakeScoringService)
    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_write_scores_to_sheet",
        lambda **kwargs: write_tabs.append(kwargs["tab_name"]) or len(kwargs["initiative_keys"]),
    )
    monkeypatch.setattr(
        "app.sheets.productops_writer.write_status_to_sheet",
        lambda _client, _spreadsheet_id, tab_name, _statuses: status_tabs.append(tab_name),
    )

    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "scoring_inputs_tab": "Scoring_Inputs"})())
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.switch_framework",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "scoring inputs"},
                "scope": {"initiative_keys": ["INIT-000001"]},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_switch_framework(db_session, ctx)
        assert result["tab"] == "Scoring_Inputs"
        assert sync_tabs == ["Scoring_Inputs"]
        assert write_tabs == ["Scoring_Inputs"]
        assert status_tabs == ["Scoring_Inputs"]
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_pm_populate_initiatives_presync_requires_explicit_target_when_multiple_backlogs(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    original_central_backlog = settings.CENTRAL_BACKLOG
    original_backlog_sheets = settings.CENTRAL_BACKLOG_SHEETS

    settings.PRODUCT_OPS = cast(Any, type("Cfg", (), {"spreadsheet_id": "sheet-1", "scoring_inputs_tab": "Scoring_Inputs"})())
    settings.CENTRAL_BACKLOG = None
    settings.CENTRAL_BACKLOG_SHEETS = [
        BacklogSheetConfig(spreadsheet_id="backlog-sheet-1", tab_name="Backlog", product_org="core"),
        BacklogSheetConfig(spreadsheet_id="backlog-sheet-2", tab_name="Backlog", product_org="growth"),
    ]

    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_populate_initiatives",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("populate should not run when presync target is ambiguous")),
    )

    try:
        ctx = ActionContext(
            payload={
                "action": "pm.populate_initiatives",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Scoring_Inputs"},
                "options": {"auto_sync_backlog_first": True},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        with pytest.raises(RuntimeError, match="ambiguous with multiple backlog targets"):
            _action_pm_populate_initiatives(db_session, ctx)
    finally:
        settings.PRODUCT_OPS = original_product_ops
        settings.CENTRAL_BACKLOG = original_central_backlog
        settings.CENTRAL_BACKLOG_SHEETS = original_backlog_sheets


def test_pm_populate_candidates_guides_user_on_wrong_tab(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_optimization_center = settings.OPTIMIZATION_CENTER
    settings.OPTIMIZATION_CENTER = cast(
        Any,
        type("Cfg", (), {"spreadsheet_id": "sheet-1", "candidates_tab": "Candidates"})(),
    )
    monkeypatch.setattr(
        "app.sheets.optimization_candidates_writer.populate_candidates_from_db",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrong-tab populate_candidates must not write")),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.populate_candidates",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Results"},
                "options": {"scenario_name": "Q2", "constraint_set_name": "Default"},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_populate_candidates(db_session, ctx)
        summary = _extract_summary("pm.populate_candidates", result)
        assert result["status"] == "skipped"
        assert result["reason"] == "wrong_tab"
        assert result["target_tab"] == "Candidates"
        assert summary["skipped"] == 1
    finally:
        settings.OPTIMIZATION_CENTER = original_optimization_center


def test_pm_save_selected_scope_all_passes_none_for_initiative_keys(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    original_product_ops = settings.PRODUCT_OPS
    captured_initiative_keys: list[Any] = []

    monkeypatch.setattr(
        "app.services.action_runner.run_flow3_sync_inputs_to_initiatives",
        lambda **kwargs: captured_initiative_keys.append(kwargs["initiative_keys"]) or 4,
    )
    monkeypatch.setattr(
        "app.sheets.productops_writer.write_status_to_productops_sheet",
        lambda *_args, **_kwargs: None,
    )

    settings.PRODUCT_OPS = cast(
        Any,
        type(
            "Cfg",
            (),
            {
                "spreadsheet_id": "sheet-1",
                "scoring_inputs_tab": "Scoring_Inputs",
                "mathmodels_tab": "MathModels",
                "params_tab": "Params",
                "metrics_config_tab": "Metrics_Config",
                "kpi_contributions_tab": "KPI_Contributions",
            },
        )(),
    )
    try:
        ctx = ActionContext(
            payload={
                "action": "pm.save_selected",
                "sheet_context": {"spreadsheet_id": "sheet-1", "tab": "Scoring_Inputs"},
                "scope": {"type": "all", "initiative_keys": []},
            },
            sheets_client=cast(Any, object()),
            llm_client=None,
        )
        result = _action_pm_save_selected(db_session, ctx)
        assert captured_initiative_keys == [None]
        assert result["saved_count"] == 4
    finally:
        settings.PRODUCT_OPS = original_product_ops


def test_flow3_sync_inputs_raises_on_batch_commit_failure(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_initiative(db_session, initiative_key="INIT-000013", title="Needs Sync")

    monkeypatch.setattr(
        "app.jobs.flow3_product_ops_job.run_flow3_preview_inputs",
        lambda spreadsheet_id=None, tab_name=None: [
            ScoringInputsRow(
                initiative_key="INIT-000013",
                active_scoring_framework="RICE",
                extras={
                    "strategic_priority_coefficient": 1.5,
                    "risk_level": "medium",
                    "time_sensitivity_score": 3.0,
                },
            )
        ],
    )

    commit_calls = {"count": 0}
    original_rollback = db_session.rollback

    def fail_first_commit() -> None:
        commit_calls["count"] += 1
        raise RuntimeError("batch commit failed")

    monkeypatch.setattr(db_session, "commit", fail_first_commit)
    monkeypatch.setattr(db_session, "rollback", original_rollback)

    with pytest.raises(RuntimeError, match="batch commit failed"):
        run_flow3_sync_inputs_to_initiatives(db_session, commit_every=1)

    assert commit_calls["count"] == 1


def test_flow3_sync_inputs_raises_on_final_commit_failure(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _create_initiative(db_session, initiative_key="INIT-000014", title="Needs Final Commit")

    monkeypatch.setattr(
        "app.jobs.flow3_product_ops_job.run_flow3_preview_inputs",
        lambda spreadsheet_id=None, tab_name=None: [
            ScoringInputsRow(
                initiative_key="INIT-000014",
                active_scoring_framework="WSJF",
                extras={
                    "strategic_priority_coefficient": 2.0,
                    "risk_level": "high",
                    "time_sensitivity_score": 5.0,
                },
            )
        ],
    )

    commit_calls = {"count": 0}
    original_rollback = db_session.rollback

    def fail_final_commit() -> None:
        commit_calls["count"] += 1
        raise RuntimeError("final commit failed")

    monkeypatch.setattr(db_session, "commit", fail_final_commit)
    monkeypatch.setattr(db_session, "rollback", original_rollback)

    with pytest.raises(RuntimeError, match="final commit failed"):
        run_flow3_sync_inputs_to_initiatives(db_session, commit_every=1_000)

    assert commit_calls["count"] == 1


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