"""Quick validation that Phase 4 config additions work"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings


def test_phase4_config():
    """Verify new ProductOps config fields are accessible"""
    config = settings.PRODUCT_OPS
    
    assert config is not None, "PRODUCT_OPS config is None - check your configuration"
    
    # Check new fields exist
    assert hasattr(config, 'mathmodels_tab'), "Missing mathmodels_tab in config"
    assert hasattr(config, 'params_tab'), "Missing params_tab in config"
    
    # Check they have values
    assert config.mathmodels_tab == "MathModels", f"Expected 'MathModels', got {config.mathmodels_tab}"
    assert config.params_tab == "Params", f"Expected 'Params', got {config.params_tab}"
    
    # Existing config still works
    assert config.scoring_inputs_tab == "Scoring_Inputs"
    assert config.spreadsheet_id, "spreadsheet_id is empty"
    
    print("✅ Phase 4 config validation passed!")
    print(f"   - Spreadsheet ID: {config.spreadsheet_id[:20]}..." if len(config.spreadsheet_id) > 20 else f"   - Spreadsheet ID: {config.spreadsheet_id}")
    print(f"   - MathModels tab: {config.mathmodels_tab}")
    print(f"   - Params tab: {config.params_tab}")
    print(f"   - Scoring tab: {config.scoring_inputs_tab}")
    print(f"   - Config tab: {config.config_tab}")
    return True


if __name__ == "__main__":
    try:
        test_phase4_config()
        print("\n✅ All checks passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)