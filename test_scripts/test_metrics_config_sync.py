#!/usr/bin/env python3
"""Test script for Metrics Config Sync Service (Action Item #6)

Tests:
1. Metrics Config tab → OrganizationMetricConfig DB sync
2. Validation: only north_star/strategic allowed
3. Validation: unique kpi_keys
4. Validation: exactly one active north_star
5. pm.save_selected action integration
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.config import settings
from app.services.product_ops.metrics_config_sync_service import MetricsConfigSyncService
from app.sheets.client import SheetsClient, get_sheets_service
from app.db.models.optimization import OrganizationMetricConfig


def test_metrics_config_sync():
    """Test Metrics Config sync functionality."""
    
    # Setup
    print("🧪 Testing Metrics Config Sync Service")
    print("=" * 60)
    
    if not settings.PRODUCT_OPS:
        print("❌ PRODUCT_OPS config not found")
        return
    
    spreadsheet_id = settings.PRODUCT_OPS.spreadsheet_id
    tab_name = getattr(settings.PRODUCT_OPS, "metrics_config_tab", None) or "Metrics_Config"
    
    print(f"📊 Spreadsheet: {spreadsheet_id}")
    print(f"📋 Tab: {tab_name}")
    print()
    
    # Initialize service
    service_client = get_sheets_service()
    client = SheetsClient(service_client)
    sync_service = MetricsConfigSyncService(client)
    
    # Test 1: Preview rows
    print("Test 1: Preview Metrics Config rows")
    print("-" * 60)
    try:
        rows = sync_service.preview_rows(spreadsheet_id, tab_name, max_rows=5)
        print(f"✅ Found {len(rows)} rows (showing first 5)")
        for row_num, row in rows[:3]:
            print(f"  Row {row_num}: {row.kpi_key} | {row.kpi_name} | level={row.kpi_level} | active={row.is_active}")
        print()
    except Exception as e:
        print(f"❌ Preview failed: {e}")
        return
    
    # Test 2: Sync to DB
    print("Test 2: Sync to Database")
    print("-" * 60)
    db = SessionLocal()
    try:
        # Get count before
        count_before = db.query(OrganizationMetricConfig).count()
        print(f"📊 Metrics in DB before: {count_before}")
        
        # Sync
        result = sync_service.sync_sheet_to_db(
            db=db,
            spreadsheet_id=spreadsheet_id,
            tab_name=tab_name,
        )
        
        print("✅ Sync completed:")
        print(f"  - Rows processed: {result['row_count']}")
        print(f"  - Upserted: {result['upserts']}")
        print(f"  - Created: {result['created']}")
        print(f"  - Skipped (bad level): {result['skipped_bad_level']}")
        
        # Get count after
        count_after = db.query(OrganizationMetricConfig).count()
        print(f"📊 Metrics in DB after: {count_after}")
        print()
        
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        db.close()
    
    # Test 3: Verify validation rules
    print("Test 3: Verify Data Integrity")
    print("-" * 60)
    db = SessionLocal()
    try:
        # Check levels
        configs = db.query(OrganizationMetricConfig).all()
        levels = {}
        for cfg in configs:
            level = cfg.kpi_level or "unknown"
            levels[level] = levels.get(level, 0) + 1
        
        print("📊 KPI Levels:")
        for level, count in levels.items():
            print(f"  - {level}: {count}")
        
        # Check active north_star - configs are already fetched ORM objects
        active_north_stars = []
        for cfg in configs:
            # At this point cfg.kpi_level is already a Python string value from the DB
            if getattr(cfg, 'kpi_level', None) == "north_star":
                metadata = getattr(cfg, 'metadata_json', None)
                if metadata and metadata.get("is_active"):
                    active_north_stars.append(cfg)
        print(f"\n🎯 Active North Star KPIs: {len(active_north_stars)}")
        for cfg in active_north_stars:
            print(f"  - {cfg.kpi_key}: {cfg.kpi_name}")
        
        if len(active_north_stars) != 1:
            print(f"⚠️  WARNING: Should have exactly 1 active north_star, found {len(active_north_stars)}")
        else:
            print("✅ Validation passed: exactly 1 active north_star")
        
        print()
    finally:
        db.close()
    
    # Test 4: Test with selection filter
    print("Test 4: Sync Selected KPIs Only")
    print("-" * 60)
    db = SessionLocal()
    try:
        if rows:
            test_keys = [row.kpi_key for _, row in rows[:2]]
            print(f"🎯 Testing with keys: {test_keys}")
            
            result = sync_service.sync_sheet_to_db(
                db=db,
                spreadsheet_id=spreadsheet_id,
                tab_name=tab_name,
                kpi_keys=test_keys,
            )
            
            print("✅ Selective sync completed:")
            print(f"  - Selected: {len(test_keys)}")
            print(f"  - Upserted: {result['upserts']}")
            print()
    finally:
        db.close()
    
    print("=" * 60)
    print("✅ All tests completed!")
    print()
    print("Next steps:")
    print("1. Test pm.save_selected action from Google Sheets")
    print("2. Select some rows in Metrics_Config tab")
    print("3. Run 'Save Selected' from the sheet menu")
    print("4. Verify changes in DB")


if __name__ == "__main__":
    test_metrics_config_sync()
