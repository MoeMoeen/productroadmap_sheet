#!/usr/bin/env python3
"""
Integration test for ScoringService.

Tests:
1. Pick first initiative from DB
2. Score with RICE framework
3. Verify Initiative fields updated (value/effort/overall scores)
4. Verify InitiativeScore history row created (if enabled)
5. Print results for manual inspection
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.db.session import SessionLocal
from app.db.models.initiative import Initiative
from app.db.models.scoring import InitiativeScore
from app.services.scoring import ScoringFramework
from app.services.scoring_service import ScoringService


def main():
    print("=== ScoringService Integration Test ===\n")
    
    # Create DB session
    db = SessionLocal()
    
    try:
        # Pick first initiative
        initiative = db.query(Initiative).order_by(Initiative.id).first()
        
        if not initiative:
            print("❌ No initiatives found in database!")
            print("   Run intake sync first to populate initiatives")
            return 1
        
        print(f"📋 Testing with initiative: {initiative.initiative_key}")
        print(f"   Title: {initiative.title}")
        print(f"   Current scores: value={initiative.value_score}, effort={initiative.effort_score}, overall={initiative.overall_score}")
        print(f"   Active framework: {initiative.active_scoring_framework}\n")
        
        # Score with RICE
        service = ScoringService(db)
        framework = ScoringFramework.RICE
        
        print(f"🔢 Computing {framework.value} score...")
        history_row = service.score_initiative(
            initiative=initiative,
            framework=framework,
            enable_history=True,  # Force history for test
        )
        
        # Commit changes
        db.commit()
        
        # Verify Initiative updated
        print(f"\n✅ Initiative scores updated:")
        print(f"   value_score:      {initiative.value_score}")
        print(f"   effort_score:     {initiative.effort_score}")
        print(f"   overall_score:    {initiative.overall_score}")
        print(f"   active_framework: {initiative.active_scoring_framework}")
        print(f"   updated_source:   {initiative.updated_source}")
        
        # Verify history row
        if history_row:
            print(f"\n✅ InitiativeScore history row created:")
            print(f"   id:               {history_row.id}")
            print(f"   initiative_id:    {history_row.initiative_id}")
            print(f"   framework:        {history_row.framework_name}")
            print(f"   overall_score:    {history_row.overall_score}")
            print(f"   inputs_json:      {history_row.inputs_json}")
            print(f"   components_json:  {history_row.components_json}")
            print(f"   warnings_json:    {history_row.warnings_json}")
        else:
            print(f"\n⚠️  No history row created (SCORING_ENABLE_HISTORY={settings.SCORING_ENABLE_HISTORY})")
        
        # Query all scores for this initiative
        all_scores = db.query(InitiativeScore).filter(
            InitiativeScore.initiative_id == initiative.id
        ).order_by(InitiativeScore.created_at.desc()).all()
        
        print(f"\n📊 Total score history entries for this initiative: {len(all_scores)}")
        for idx, score in enumerate(all_scores[:3], start=1):  # Show most recent 3
            print(f"   {idx}. {score.framework_name} @ {score.created_at}: {score.overall_score}")
        
        print("\n🎉 Test completed successfully!")
        return 0
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
