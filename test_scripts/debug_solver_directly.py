#!/usr/bin/env python3
"""
Debug solver directly by building the optimization problem and calling the solver
with detailed logging to see why INIT-003 + INIT-005 solution is not found.
"""
import asyncio
import logging
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.models.optimization import OptimizationScenario, OptimizationConstraintSet
from app.services.optimization.optimization_problem_builder import build_optimization_problem
from app.services.solvers.ortools_cp_sat_adapter import OrtoolsCpSatSolverAdapter, CpSatConfig

# Enable verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s [%(name)s] %(message)s",
    stream=sys.stdout,
)

# Ensure local `app` package is importable in editors/Pylance by adding project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    settings = Settings()
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    # --- SYNC LATEST SHEET DATA BEFORE FETCHING FROM DB ---
    print("\nSyncing latest scenarios, constraints, and candidates from sheet...")
    import json
    from app.sheets.client import get_sheets_service, SheetsClient
    from app.services.optimization.optimization_sync_service import sync_scenarios_from_sheet, sync_constraint_sets_from_sheets, sync_candidates_from_sheet
    config_path = "optimization_center_sheet_config.json"
    with open(config_path, "r") as f:
        sheet_cfg = json.load(f)
    sheets_service = get_sheets_service()
    sheets_client = SheetsClient(sheets_service)
    sync_scenarios_from_sheet(
        sheets_client,
        sheet_cfg["spreadsheet_id"],
        sheet_cfg["scenario_config_tab"],
        db
    )
    sync_constraint_sets_from_sheets(
        sheets_client,
        sheet_cfg["spreadsheet_id"],
        sheet_cfg["constraints_tab"],
        sheet_cfg["targets_tab"],
        db
    )
    sync_candidates_from_sheet(
        sheets_client,
        sheet_cfg["spreadsheet_id"],
        sheet_cfg["candidates_tab"],
        None,
        50,
        db
    )
    print("✓ Sync complete. Proceeding with up-to-date DB data.")
    
    print("=" * 80)
    print("DIRECT SOLVER DEBUG")
    print("=" * 80)
    
    # 1. Get scenario and constraint set from DB
    scenario = db.query(OptimizationScenario).filter_by(name="2026-Q1 Growth").first()
    constraint_set = db.query(OptimizationConstraintSet).filter_by(name="Baseline").first()
    
    if not scenario:
        print("ERROR: Scenario '2026-Q1 Growth' not found!")
        return
    if not constraint_set:
        print("ERROR: Constraint set 'Baseline' not found!")
        return
    
    print(f"\n✓ Found scenario: {scenario.name}")
    print(f"  Capacity: {scenario.capacity_total_tokens} tokens")
    print(f"  Objective mode: {scenario.objective_mode}")
    print(f"  Weights: {scenario.objective_weights_json}")
    
    print(f"\n✓ Found constraint set: {constraint_set.name}")
    print(f"  Mandatory: {constraint_set.mandatory_initiatives_json}")
    print(f"  Bundles: {constraint_set.bundles_json}")
    print(f"  Exclusions: {constraint_set.exclusions_pairs_json}")
    print(f"  Prerequisites: {constraint_set.prerequisites_json}")
    print(f"  Floors: {constraint_set.floors_json}")
    print(f"  Caps: {constraint_set.caps_json}")
    
    # 2. Build optimization problem
    print("\n" + "=" * 80)
    print("BUILDING OPTIMIZATION PROBLEM")
    print("=" * 80)
    
    problem = build_optimization_problem(
        db=db,
        scenario_name=str(scenario.name),
        constraint_set_name=str(constraint_set.name),
        scope_type="selected_only",
        selected_initiative_keys=["INIT-0001", "INIT-0003", "INIT-0004", "INIT-0005", "INIT-0006"],
    )
    
    print(f"\n✓ Problem built")
    print(f"  Candidates: {len(problem.candidates)}")
    print(f"  Scenario: {problem.scenario_name}")
    print(f"  Constraint set: {problem.constraint_set_name}")
    
    print("\nCandidate details:")
    for c in problem.candidates:
        print(f"  {c.initiative_key}:")
        print(f"    Tokens: {c.engineering_tokens}")
        print(f"    Country: {c.country}")
        print(f"    Department: {c.department}")
        if c.kpi_contributions:
            print(f"    KPI contributions:")
            for k, v in c.kpi_contributions.items():
                print(f"      {k}: {v}")
        else:
            print(f"    KPI contributions: None")
    
    # 3. Call solver with debug config
    print("\n" + "=" * 80)
    print("CALLING SOLVER")
    print("=" * 80)
    
    config = CpSatConfig(
        max_time_seconds=30.0,
        num_workers=8,
        log_search_progress=True,  # Enable CP-SAT internal logging
    )
    
    solver = OrtoolsCpSatSolverAdapter(config=config)
    solution = solver.solve(problem)
    
    print("\n" + "=" * 80)
    print("SOLVER RESULT")
    print("=" * 80)
    print(f"Status: {solution.status}")
    print(f"Selected count: {len([s for s in solution.selected if s.selected])}")
    print(f"Capacity used: {solution.capacity_used_tokens}")
    print(f"Objective value: {solution.objective_value}")
    
    if solution.selected:
        print("\nSelected initiatives:")
        for item in solution.selected:
            if item.selected:
                print(f"  ✓ {item.initiative_key} ({item.allocated_tokens} tokens)")
        
        print("\nNot selected:")
        for item in solution.selected:
            if not item.selected:
                print(f"  ✗ {item.initiative_key}")
    
    import json
    if solution.diagnostics:
        print("\nDiagnostics:")
        for key, val in solution.diagnostics.items():
            # Pretty-print targets or any dict/list values
            if key.lower().startswith("target") or isinstance(val, (dict, list)):
                pretty = json.dumps(val, indent=2, ensure_ascii=False)
                print(f"  {key}:\n{pretty}")
            else:
                print(f"  {key}: {val}")
    
    print("\n" + "=" * 80)
    print("MANUAL FEASIBILITY CHECK")
    print("=" * 80)
    
    # Check if INIT-0003 + INIT-0005 would be feasible
    print("\nOption: INIT-0003 + INIT-0005")
    init_0003 = next((c for c in problem.candidates if c.initiative_key == "INIT-0003"), None)
    init_0005 = next((c for c in problem.candidates if c.initiative_key == "INIT-0005"), None)

    if init_0003 and init_0005:
        total_tokens = init_0003.engineering_tokens + init_0005.engineering_tokens
        total_gmv = init_0003.kpi_contributions.get('north_star_gmv', 0) + init_0005.kpi_contributions.get('north_star_gmv', 0)

        print(f"  {init_0003.initiative_key}: {init_0003.engineering_tokens} tokens ({init_0003.country}/{init_0003.department})")
        print(f"  {init_0005.initiative_key}: {init_0005.engineering_tokens} tokens ({init_0005.country}/{init_0005.department})")
        print(f"  Total tokens: {total_tokens}")
        print(f"  Total GMV: {total_gmv}")

        # Check constraints
        print("\n  Constraint checks:")
        print(f"    Mandatory {init_0003.initiative_key}: ✓ (included)")
        print(f"    Exclusion INIT-0001/{init_0003.initiative_key}: ✓ (INIT-0001 not selected)")
        print(f"    Bundle INIT-0004/INIT-0006: ✓ (neither selected)")
        print(f"    Prerequisite INIT-0006→{init_0005.initiative_key}: ✓ (INIT-0006 not selected)")

        # Core department
        core_tokens = 0
        if init_0003.department == "Core":
            core_tokens += init_0003.engineering_tokens
        if init_0005.department == "Core":
            core_tokens += init_0005.engineering_tokens
        print(f"    Core cap (400): {core_tokens} ✓" if core_tokens <= 400 else f"    Core cap (400): {core_tokens} ✗")

        # UK floor
        uk_tokens = 0
        if init_0005.country == "UK":
            uk_tokens += init_0005.engineering_tokens
        print(f"    UK floor (200): {uk_tokens} ✓" if uk_tokens >= 200 else f"    UK floor (200): {uk_tokens} ✗")

        print(f"    Total capacity (1000): {total_tokens} ✓" if total_tokens <= 1000 else f"    Total capacity (1000): {total_tokens} ✗")
        print(f"    GMV floor (400): {total_gmv} ✓" if total_gmv >= 400 else f"    GMV floor (400): {total_gmv} ✗")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
