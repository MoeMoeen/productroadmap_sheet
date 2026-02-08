#!/usr/bin/env python3
"""End-to-end test for pm.explain_selection action against real Google Sheets."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.services.action_runner import enqueue_action_run, execute_next_queued_run
from app.config import settings
import json


def test_explain_selection_e2e():
    """Test pm.explain_selection against real Optimization Center sheet."""
    
    print("=" * 80)
    print("PM Explain Selection - End-to-End Test")
    print("=" * 80)
    print()
    
    # Verify config
    if not settings.OPTIMIZATION_CENTER:
        print("❌ OPTIMIZATION_CENTER not configured")
        return
    
    print(f"Spreadsheet: {settings.OPTIMIZATION_CENTER.spreadsheet_id}")
    print(f"Candidates Tab: {settings.OPTIMIZATION_CENTER.candidates_tab}")
    print()
    
    # Create payload for explain_selection action
    # This will read candidates with is_selected_for_run=TRUE from the sheet
    payload = {
        "action": "pm.explain_selection",
        "options": {
            "scenario_name": "2026-Q1 Growth",  # Update this to match your scenario
            "constraint_set_name": "Baseline",   # Update this to match your constraint set
        },
        "scope": {},  # Empty scope means read from sheet's is_selected_for_run column
        "requested_by": {
            "user_email": "test@example.com",
            "ui": "manual_test",
        },
    }
    
    print("Action Payload:")
    print(json.dumps(payload, indent=2))
    print()
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Enqueue the action
        print("Step 1: Enqueuing action...")
        action_run = enqueue_action_run(db, payload)
        print(f"✓ Enqueued with run_id: {action_run.run_id}")
        print(f"  Status: {action_run.status}")
        print()
        
        # Execute the action
        print("Step 2: Executing action (reading from real sheet)...")
        print()
        executed_run = execute_next_queued_run(db)
        
        if not executed_run:
            print("❌ No action run was executed")
            return
        
        print()
        print("=" * 80)
        print("Execution Complete")
        print("=" * 80)
        print()
        print(f"Run ID: {executed_run.run_id}")
        print(f"Status: {executed_run.status}")
        print()
        
        if executed_run.result_json is not None:
            print("Result:")
            print(json.dumps(executed_run.result_json, indent=2))
            print()
            
            result = executed_run.result_json
            raw_result = result.get('raw', {}) if isinstance(result, dict) else {}
            
            # Summary
            print("=" * 80)
            print("Summary")
            print("=" * 80)
            print(f"PM Job: {raw_result.get('pm_job')}")
            print(f"Status: {raw_result.get('status')}")
            print(f"Scenario: {raw_result.get('scenario_name')}")
            print(f"Constraint Set: {raw_result.get('constraint_set_name')}")
            print(f"Candidates Evaluated: {raw_result.get('input_candidates_count')}")
            print(f"Is Feasible: {raw_result.get('is_feasible')}")
            print(f"Violations: {raw_result.get('violations_count')}")
            print()
            
            if raw_result.get('evaluation'):
                eval_data = raw_result['evaluation']
                print("Evaluation Details:")
                print(f"  Selected Keys: {eval_data.get('selected_keys')}")
                print(f"  Totals: {eval_data.get('totals')}")
                if eval_data.get('violations'):
                    print("  Violations:")
                    for v in eval_data['violations']:
                        print(f"    - [{v.get('severity')}] {v.get('code')}: {v.get('message')}")
                print()
            
            if raw_result.get('repair_plan'):
                repair = raw_result['repair_plan']
                print("Repair Plan:")
                print(f"  Initial Selected: {repair.get('initial_selected')}")
                print(f"  Final Selected: {repair.get('final_selected')}")
                print(f"  Steps: {len(repair.get('steps', []))}")
                if repair.get('steps'):
                    for i, step in enumerate(repair['steps'], 1):
                        print(f"    {i}. {step.get('action')}: {step.get('initiative_key')} - {step.get('reason')}")
                print()
            
            if str(executed_run.status) == "success":
                print("✅ TEST PASSED")
            else:
                print(f"⚠️  Test completed with status: {executed_run.status}")
                if raw_result.get('error'):
                    print(f"Error: {raw_result.get('error')}")
        
        else:
            print("⚠️  No result JSON found")
            if executed_run.error_message:
                print(f"Error: {executed_run.error_message}")
    
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


if __name__ == "__main__":
    test_explain_selection_e2e()
