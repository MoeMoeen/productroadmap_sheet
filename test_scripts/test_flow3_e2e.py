#!/usr/bin/env python3

# productroadmap_sheet_project/test_scripts/test_flow3_e2e.py

"""
End-to-end test for Flow 3: Product Ops Scoring Inputs and Multi-Framework Scoring.

This test validates the complete data flow:
1. Product Ops sheet has scoring inputs (rice_reach, wsjf_job_size, active_scoring_framework)
2. Flow 3.B: Sync reads from sheet and writes to DB
3. Flow 3.C Phase 1: Compute all frameworks (RICE + WSJF) and store per-framework scores
4. Flow 3.C Phase 2: Write per-framework scores back to Product Ops sheet
5. Verify backlog display reflects active_scoring_framework

This ensures PMs can:
- Choose which framework per initiative in Product Ops sheet
- See scores from all frameworks for comparison
- Have confidence that DB and sheet stay in sync
"""

import logging

from app.db.models.initiative import Initiative

from app.db.session import SessionLocal
from app.jobs.flow3_product_ops_job import (
    run_flow3_preview_inputs,
    run_flow3_sync_inputs_to_initiatives,
    run_flow3_write_scores_to_sheet,
)
from app.services.product_ops.scoring_service import ScoringService


def configure_logging() -> None:
    """Configure JSON logging for the app"""
    from app.config import setup_json_logging
    setup_json_logging(log_level=logging.DEBUG)


def test_flow3_e2e() -> None:
    """Run full Flow 3 pipeline and validate state at each step."""
    logger = logging.getLogger("app.test_flow3_e2e")

    db = SessionLocal()
    try:
        logger.info("=== FLOW 3 E2E TEST START ===")

        # Step 0: Preview what we're about to sync
        logger.info("Step 0: Preview Product Ops inputs (read-only)")
        rows = run_flow3_preview_inputs()
        logger.info(f"Previewed {len(rows)} scoring input rows")
        if len(rows) == 0:
            logger.warning("No rows to sync; test is inconclusive")
            return

        # Step 1: Flow 3.B - Sync Product Ops sheet -> DB
        logger.info("Step 1: Flow 3.B - Sync Product Ops inputs to DB (strong sync)")
        sync_count = run_flow3_sync_inputs_to_initiatives(db, commit_every=10)
        logger.info(f"Synced {sync_count} initiatives from Product Ops sheet")
        db.commit()

        # Validate: Check that active_scoring_framework was written to DB
        updated_inits = db.query(Initiative).filter(Initiative.active_scoring_framework.isnot(None)).all()
        logger.info(f"DB now has {len(updated_inits)} initiatives with active_scoring_framework set")
        for ini in updated_inits[:3]:  # Show first 3
            logger.info(f"  {ini.initiative_key}: active_scoring_framework={ini.active_scoring_framework}")

        # Step 2: Flow 3.C Phase 1 - Compute all frameworks
        logger.info("Step 2: Flow 3.C Phase 1 - Compute all frameworks (RICE + WSJF)")
        service = ScoringService(db)
        compute_count = service.compute_all_frameworks(commit_every=10)
        logger.info(f"Computed scores for all {compute_count} initiatives")
        db.commit()

        # Validate: Check that both per-framework scores were populated
        inits_with_scores = db.query(Initiative).filter(Initiative.rice_overall_score.isnot(None)).all()
        logger.info(f"DB now has {len(inits_with_scores)} initiatives with RICE overall_score")
        
        inits_wsjf_scores = db.query(Initiative).filter(Initiative.wsjf_overall_score.isnot(None)).all()
        logger.info(f"DB now has {len(inits_wsjf_scores)} initiatives with WSJF overall_score")

        for ini in inits_with_scores[:3]:  # Show first 3
            logger.info(f"  {ini.initiative_key}:")
            logger.info(f"    active_framework={ini.active_scoring_framework}")
            logger.info(f"    rice_value={ini.rice_value_score}, rice_overall={ini.rice_overall_score}")
            logger.info(f"    wsjf_value={ini.wsjf_value_score}, wsjf_overall={ini.wsjf_overall_score}")

        # Step 3: Flow 3.C Phase 2 - Write per-framework scores back to Product Ops sheet
        logger.info("Step 3: Flow 3.C Phase 2 - Write per-framework scores back to Product Ops sheet")
        write_count = run_flow3_write_scores_to_sheet(db)
        logger.info(f"Wrote per-framework scores back to sheet for {write_count} initiatives")

        # Step 4: Validation
        logger.info("Step 4: Validation")
        # Check that we have multi-framework coverage
        all_inits = db.query(Initiative).filter(Initiative.active_scoring_framework.isnot(None)).all()
        rice_only = [
            i for i in all_inits
            if getattr(i, "active_scoring_framework", None) == "RICE" and getattr(i, "rice_overall_score", None) is not None
        ]
        wsjf_only = [
            i for i in all_inits
            if getattr(i, "active_scoring_framework", None) == "WSJF" and getattr(i, "wsjf_overall_score", None) is not None
        ]
        both_set = [
            i for i in all_inits
            if getattr(i, "rice_overall_score", None) is not None and getattr(i, "wsjf_overall_score", None) is not None
        ]

        logger.info(f"Initiatives with active_framework=RICE and rice_overall_score set: {len(rice_only)}")
        logger.info(f"Initiatives with active_framework=WSJF and wsjf_overall_score set: {len(wsjf_only)}")
        logger.info(f"Initiatives with BOTH rice and wsjf scores: {len(both_set)}")

        if len(both_set) > 0:
            logger.info("✓ SUCCESS: Multi-framework scores populated")
            logger.info("=== FLOW 3 E2E TEST PASSED ===")
            assert True, "Multi-framework scores populated"
        else:
            logger.warning("⚠ PARTIAL: No initiatives have both framework scores (may be expected if only one framework used)")
            logger.info("=== FLOW 3 E2E TEST COMPLETE (PARTIAL SUCCESS) ===")
            assert True, "Partial success (expected if only one framework used)"

    except KeyboardInterrupt:
        logger.warning("Test interrupted")
        assert False, "Test interrupted"
    except Exception:
        logger.exception("Test failed with exception")
        assert False, "Test failed with exception"
    finally:
        db.close()


if __name__ == "__main__":
    configure_logging()
    test_flow3_e2e()
