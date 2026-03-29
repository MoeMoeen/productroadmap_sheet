#!/usr/bin/env python3
"""
Q2 2026 Qlub Simulation - Sheet Population Script

This script populates Google Sheets with realistic sample data for the
Q2 2026 Qlub roadmapping simulation end-to-end test.

Sheets populated:
1. Metrics_Config (ProductOps) - 5 KPIs (1 north star + 4 strategic)
2. Central Backlog - 25 initiatives (basic fields for all)
3. MathModels (ProductOps) - 6 enriched initiatives with formulas
4. Params (ProductOps) - Parameters for 6 enriched initiatives
5. Optimization Center - Scenarios, Constraints, Targets

Usage:
    python test_scripts/q2_2026_simulation_populate.py --all
    python test_scripts/q2_2026_simulation_populate.py --metrics-config
    python test_scripts/q2_2026_simulation_populate.py --backlog
    python test_scripts/q2_2026_simulation_populate.py --mathmodels
    python test_scripts/q2_2026_simulation_populate.py --params
    python test_scripts/q2_2026_simulation_populate.py --optimization
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sheets.client import SheetsClient, get_sheets_service
from app.sheets.layout import data_start_row
from app.config import settings

# ============================================================================
# CONFIGURATION
# ============================================================================

# Load sheet configs
PROJECT_ROOT = Path(__file__).parent.parent

with open(PROJECT_ROOT / "product_ops_config.json") as f:
    PRODUCTOPS_CONFIG = json.load(f)

with open(PROJECT_ROOT / "optimization_center_sheet_config.json") as f:
    OPTIMIZATION_CONFIG = json.load(f)

PRODUCTOPS_SHEET_ID = PRODUCTOPS_CONFIG["spreadsheet_id"]
OPTIMIZATION_SHEET_ID = OPTIMIZATION_CONFIG["spreadsheet_id"]

# Central Backlog - get from settings or use a default
def get_central_backlog_config():
    if settings.CENTRAL_BACKLOG:
        return settings.CENTRAL_BACKLOG.spreadsheet_id, settings.CENTRAL_BACKLOG.tab_name or "Backlog"
    # Fallback: use ProductOps sheet with a Backlog tab
    return PRODUCTOPS_SHEET_ID, "Backlog"

# ============================================================================
# KPI DEFINITIONS (Metrics_Config)
# ============================================================================

METRICS_CONFIG_ROWS = [
    {
        "kpi_key": "qlub_revenue",
        "kpi_name": "Qlub Revenue",
        "kpi_level": "north_star",
        "unit": "currency_per_month",
        "description": "Revenue captured by Qlub from processed GMV times monetization rate.",
        "is_active": "TRUE",
        "notes": "Single active north star for Q2 2026 simulation.",
    },
    {
        "kpi_key": "active_restaurants",
        "kpi_name": "Active Restaurants",
        "kpi_level": "strategic",
        "unit": "count",
        "description": "Number of active restaurants live on Qlub in the period.",
        "is_active": "TRUE",
        "notes": "Strategic growth KPI.",
    },
    {
        "kpi_key": "net_adoption_rate",
        "kpi_name": "Net Adoption Rate",
        "kpi_level": "strategic",
        "unit": "ratio",
        "description": "Share of total restaurant GMV effectively processed through Qlub after gross adoption and checkout completion effects.",
        "is_active": "TRUE",
        "notes": "Strategic product-usage KPI.",
    },
    {
        "kpi_key": "average_order_value",
        "kpi_name": "Average Order Value",
        "kpi_level": "strategic",
        "unit": "currency_per_order",
        "description": "Average value of a restaurant transaction/order.",
        "is_active": "TRUE",
        "notes": "Strategic economics KPI.",
    },
    {
        "kpi_key": "monthly_diners_channeled_via_qlub",
        "kpi_name": "Monthly Diners Channeled via Qlub",
        "kpi_level": "strategic",
        "unit": "diners_per_month",
        "description": "Actual diners/customers channeled to restaurants through Qlub discovery or demand-generation mechanisms.",
        "is_active": "TRUE",
        "notes": "Strategic traffic-generation KPI.",
    },
]

# ============================================================================
# ALL 25 INITIATIVES (Central Backlog)
# ============================================================================

ALL_INITIATIVES = [
    # 1. Restaurant Acquisition / Expansion (3)
    {
        "initiative_key": "INIT-RA-001",
        "title": "Self-Serve Restaurant Onboarding Flow",
        "description": "Enable restaurants to onboard without sales intervention via a fully digital onboarding flow.",
        "department": "Product",
        "country": "Global",
        "bucket": "Restaurant Acquisition",
        "immediate_kpi_key": "onboarding_conversion_rate",
        "target_kpi": "active_restaurants",
        "engineering_tokens": 180,
        "deadline": "2026-05-15",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-RA-002",
        "title": "Sales CRM + Pipeline Automation",
        "description": "Automate lead tracking, conversion stages, and performance analytics for sales teams.",
        "department": "Sales",
        "country": "UAE",
        "bucket": "Restaurant Acquisition",
        "immediate_kpi_key": "sales_pipeline_conversion_rate",
        "target_kpi": "active_restaurants",
        "engineering_tokens": 120,
        "deadline": "2026-04-30",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-RA-003",
        "title": "Geo Expansion Playbook (2 New Cities)",
        "description": "Launch Qlub in two new cities with localized onboarding and operational support.",
        "department": "Leadership",
        "country": "KSA",
        "bucket": "Restaurant Acquisition",
        "immediate_kpi_key": "new_city_restaurant_activations",
        "target_kpi": "active_restaurants",
        "engineering_tokens": 220,
        "deadline": "2026-06-20",
        "is_mandatory": False,
    },
    # 2. Adoption / Activation (3)
    {
        "initiative_key": "INIT-AA-001",
        "title": "QR Code Table Visibility Optimization",
        "description": "Improve QR placement and visibility to increase scan rates and adoption.",
        "department": "Ops",
        "country": "Turkey",
        "bucket": "Adoption",
        "immediate_kpi_key": "gross_adoption_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 90,
        "deadline": "2026-04-20",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-AA-002",
        "title": "Waiter Training App",
        "description": "Mobile training tool to improve staff ability to promote Qlub usage.",
        "department": "Ops",
        "country": "UAE",
        "bucket": "Adoption",
        "immediate_kpi_key": "gross_adoption_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 140,
        "deadline": "2026-05-30",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-AA-003",
        "title": "Smart QR Nudging During Dining",
        "description": "Contextual prompts encouraging diners to pay via Qlub during dining.",
        "department": "Product",
        "country": "Singapore",
        "bucket": "Adoption",
        "immediate_kpi_key": "gross_adoption_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 110,
        "deadline": "2026-06-10",
        "is_mandatory": False,
    },
    # 3. Checkout / Payment UX (3)
    {
        "initiative_key": "INIT-CP-001",
        "title": "1-Tap Payment Optimization",
        "description": "Reduce friction in checkout to improve completion rates.",
        "department": "Tech",
        "country": "Global",
        "bucket": "Checkout",
        "immediate_kpi_key": "checkout_completion_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 160,
        "deadline": "2026-05-25",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-CP-002",
        "title": "Multi-Payment Method Expansion",
        "description": "Add Apple Pay, Google Pay, and local wallets to improve payment success.",
        "department": "Tech",
        "country": "Hong Kong",
        "bucket": "Checkout",
        "immediate_kpi_key": "checkout_completion_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 200,
        "deadline": "2026-06-15",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-CP-003",
        "title": "Payment Failure Recovery Flow",
        "description": "Automatically retry or redirect failed payments to improve completion.",
        "department": "Tech",
        "country": "US",
        "bucket": "Checkout",
        "immediate_kpi_key": "checkout_completion_rate",
        "target_kpi": "net_adoption_rate",
        "engineering_tokens": 130,
        "deadline": "2026-05-10",
        "is_mandatory": False,
    },
    # 4. Qlub Discovery / Diner Channeling (3)
    {
        "initiative_key": "INIT-DG-001",
        "title": "Restaurant Discovery Feed",
        "description": "Build a personalized discovery feed for diners.",
        "department": "Product",
        "country": "Global",
        "bucket": "Discovery",
        "immediate_kpi_key": "qlub_discovery_traffic",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 250,
        "deadline": "2026-06-25",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-DG-002",
        "title": "Incentive Engine for Diner Acquisition",
        "description": "Offer discounts and incentives to drive traffic to restaurants.",
        "department": "Marketing",
        "country": "UAE",
        "bucket": "Discovery",
        "immediate_kpi_key": "triggered_qlub_discovery_traffic",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 210,
        "deadline": "2026-05-30",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-DG-003",
        "title": "Referral & Social Sharing System",
        "description": "Enable diners to refer others and share restaurant experiences.",
        "department": "Marketing",
        "country": "Turkey",
        "bucket": "Discovery",
        "immediate_kpi_key": "organic_qlub_discovery_traffic",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 160,
        "deadline": "2026-06-05",
        "is_mandatory": False,
    },
    # 5. Retention / Loyalty (3)
    {
        "initiative_key": "INIT-RL-001",
        "title": "Qlub Loyalty Wallet",
        "description": "Central wallet for rewards, cashback, and points.",
        "department": "Product",
        "country": "Global",
        "bucket": "Retention",
        "immediate_kpi_key": "repeat_rate",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 260,
        "deadline": "2026-06-30",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-RL-002",
        "title": "Personalized Offers Engine",
        "description": "Targeted offers based on diner behavior and preferences.",
        "department": "Data",
        "country": "US",
        "bucket": "Retention",
        "immediate_kpi_key": "repeat_rate",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 220,
        "deadline": "2026-06-10",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-RL-003",
        "title": "Push Notification Re-engagement",
        "description": "Bring inactive users back via smart notifications.",
        "department": "Marketing",
        "country": "KSA",
        "bucket": "Retention",
        "immediate_kpi_key": "repeat_rate",
        "target_kpi": "monthly_diners_channeled_via_qlub",
        "engineering_tokens": 120,
        "deadline": "2026-05-20",
        "is_mandatory": False,
    },
    # 6. Monetization (4)
    {
        "initiative_key": "INIT-MZ-001",
        "title": "Dynamic Commission Pricing",
        "description": "Adjust commission rates based on restaurant segment and demand.",
        "department": "Finance",
        "country": "Global",
        "bucket": "Monetization",
        "immediate_kpi_key": "qlub_monetization_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 180,
        "deadline": "2026-06-20",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-MZ-002",
        "title": "Premium Restaurant Placement",
        "description": "Paid visibility in discovery feed.",
        "department": "Marketing",
        "country": "Singapore",
        "bucket": "Monetization",
        "immediate_kpi_key": "qlub_monetization_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 150,
        "deadline": "2026-05-25",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-MZ-003",
        "title": "Restaurant Subscription Model",
        "description": "Monthly SaaS subscription for advanced analytics and tools.",
        "department": "Finance",
        "country": "UAE",
        "bucket": "Monetization",
        "immediate_kpi_key": "qlub_monetization_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 200,
        "deadline": "2026-06-15",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-MZ-004",
        "title": "Tier-Based Diner Loyalty Club with Subscription Plans",
        "description": "Paid subscription tiers for diners offering exclusive benefits, rewards, and experiences.",
        "department": "Product",
        "country": "Global",
        "bucket": "Monetization",
        "immediate_kpi_key": "qlub_monetization_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 260,
        "deadline": "2026-06-30",
        "is_mandatory": False,
    },
    # 7. AOV Optimization (3)
    {
        "initiative_key": "INIT-AOV-001",
        "title": "Smart Upsell During Payment Flow",
        "description": "Recommend add-ons during checkout to increase basket size.",
        "department": "Product",
        "country": "US",
        "bucket": "AOV",
        "immediate_kpi_key": "average_order_value",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 140,
        "deadline": "2026-05-30",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-AOV-002",
        "title": "Menu Bundling Recommendations",
        "description": "Suggest bundles and combos to increase order value.",
        "department": "Data",
        "country": "Hong Kong",
        "bucket": "AOV",
        "immediate_kpi_key": "average_order_value",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 120,
        "deadline": "2026-05-15",
        "is_mandatory": False,
    },
    {
        "initiative_key": "INIT-AOV-003",
        "title": "Dynamic Pricing Optimization",
        "description": "Optimize pricing and discount strategies to maximize AOV.",
        "department": "Finance",
        "country": "Turkey",
        "bucket": "AOV",
        "immediate_kpi_key": "average_order_value",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 200,
        "deadline": "2026-06-20",
        "is_mandatory": False,
    },
    # 8. Mandatory / Platform / Reliability (3)
    {
        "initiative_key": "INIT-MP-001",
        "title": "Payment Compliance Upgrade",
        "description": "Ensure compliance with new financial regulations.",
        "department": "Finance",
        "country": "Qatar",
        "bucket": "Mandatory",
        "immediate_kpi_key": "qlub_processed_gmv",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 180,
        "deadline": "2026-04-30",
        "is_mandatory": True,
    },
    {
        "initiative_key": "INIT-MP-002",
        "title": "System Reliability & Uptime Improvement",
        "description": "Improve system uptime and reduce downtime.",
        "department": "Tech",
        "country": "Global",
        "bucket": "Mandatory",
        "immediate_kpi_key": "checkout_completion_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 200,
        "deadline": "2026-05-30",
        "is_mandatory": True,
    },
    {
        "initiative_key": "INIT-MP-003",
        "title": "Fraud Detection & Risk Engine",
        "description": "Detect fraudulent transactions and reduce losses.",
        "department": "Tech",
        "country": "US",
        "bucket": "Mandatory",
        "immediate_kpi_key": "fraud_loss_rate",
        "target_kpi": "qlub_revenue",
        "engineering_tokens": 180,
        "deadline": "2026-06-10",
        "is_mandatory": True,
    },
]

# ============================================================================
# ENRICHED INITIATIVES - Math Models (6 initiatives)
# ============================================================================

MATHMODELS_ROWS = [
    # 1. INIT-RA-001 - Self-Serve Restaurant Onboarding Flow
    {
        "initiative_key": "INIT-RA-001",
        "model_name": "self_serve_onboarding_uplift_model",
        "target_kpi_key": "active_restaurants",
        "immediate_kpi_key": "onboarding_conversion_rate",
        "metric_chain_text": "onboarding_conversion_rate → new_restaurants → active_restaurants",
        "formula_text": "lead_volume * (conversion_rate_after - conversion_rate_before)",
        "assumptions_text": "Lead volume remains stable. Conversion uplift is causal from self-serve onboarding. No bottleneck in onboarding capacity. All new restaurants become active within the period.",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
    # 2. INIT-DG-002 - Incentive Engine for Diner Acquisition
    {
        "initiative_key": "INIT-DG-002",
        "model_name": "incentive_engine_diner_uplift_model",
        "target_kpi_key": "monthly_diners_channeled_via_qlub",
        "immediate_kpi_key": "triggered_qlub_discovery_traffic",
        "metric_chain_text": "triggered_qlub_discovery_traffic → discovery_conversion_rate → monthly_diners_channeled_via_qlub",
        "formula_text": "traffic_uplift * discovery_conversion_rate",
        "assumptions_text": "Conversion rate remains stable. Incentives only affect traffic, not conversion rate. Traffic uplift is incremental (not cannibalized). No supply constraint on restaurants.",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
    # 3. INIT-AOV-001 - Smart Upsell During Payment Flow
    {
        "initiative_key": "INIT-AOV-001",
        "model_name": "smart_upsell_revenue_model",
        "target_kpi_key": "qlub_revenue",
        "immediate_kpi_key": "average_order_value",
        "metric_chain_text": "average_order_value → restaurant_gmv → qlub_processed_gmv → qlub_revenue",
        "formula_text": "delta_aov * monthly_transactions * net_adoption_rate * monetization_rate",
        "assumptions_text": "Transaction volume remains stable. Upsell affects only AOV (not traffic or conversion). Adoption rate unaffected. Monetization rate unchanged. Upsell is incremental (no substitution).",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
    # 4. INIT-MZ-001 - Dynamic Commission Pricing
    {
        "initiative_key": "INIT-MZ-001",
        "model_name": "dynamic_commission_revenue_model",
        "target_kpi_key": "qlub_revenue",
        "immediate_kpi_key": "qlub_monetization_rate",
        "metric_chain_text": "monetization_rate → qlub_revenue",
        "formula_text": "base_processed_gmv * (monetization_rate_after - monetization_rate_before)",
        "assumptions_text": "No impact on transaction volume. No churn due to higher commission. Adoption rate remains constant.",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
    # 5. INIT-MP-003 - Fraud Detection & Risk Engine
    {
        "initiative_key": "INIT-MP-003",
        "model_name": "fraud_reduction_revenue_model",
        "target_kpi_key": "qlub_revenue",
        "immediate_kpi_key": "fraud_loss_rate",
        "metric_chain_text": "fraud_loss_rate → recovered_gmv → qlub_revenue",
        "formula_text": "base_processed_gmv * (fraud_rate_before - fraud_rate_after) * monetization_rate",
        "assumptions_text": "Fraud reduction directly translates to recoverable GMV. No increase in false positives affecting conversion. Monetization rate unchanged.",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
    # 6. INIT-RL-003 - Push Notification Re-engagement
    {
        "initiative_key": "INIT-RL-003",
        "model_name": "push_reengagement_diner_model",
        "target_kpi_key": "monthly_diners_channeled_via_qlub",
        "immediate_kpi_key": "repeat_rate",
        "metric_chain_text": "repeat_rate → returning_users → monthly_diners_channeled_via_qlub",
        "formula_text": "existing_qlub_customer_base * (repeat_rate_after - repeat_rate_before)",
        "assumptions_text": "Existing customer base remains stable. No overlap with acquisition initiatives. Repeat visits convert to diners.",
        "is_primary": "TRUE",
        "approved_by_user": "TRUE",
    },
]

# ============================================================================
# ENRICHED INITIATIVES - Parameters (6 initiatives)
# ============================================================================

PARAMS_ROWS = [
    # 1. INIT-RA-001 params
    {"initiative_key": "INIT-RA-001", "param_name": "lead_volume", "value": "500", "unit": "leads/month", "description": "Monthly restaurant leads entering pipeline", "approved": "TRUE"},
    {"initiative_key": "INIT-RA-001", "param_name": "conversion_rate_before", "value": "0.08", "unit": "ratio", "description": "Current onboarding conversion rate (baseline)", "approved": "TRUE"},
    {"initiative_key": "INIT-RA-001", "param_name": "conversion_rate_after", "value": "0.12", "unit": "ratio", "description": "Expected conversion rate after self-serve flow", "approved": "TRUE"},
    
    # 2. INIT-DG-002 params
    {"initiative_key": "INIT-DG-002", "param_name": "traffic_uplift", "value": "120000", "unit": "users/month", "description": "Incremental monthly discovery traffic from incentives", "approved": "TRUE"},
    {"initiative_key": "INIT-DG-002", "param_name": "discovery_conversion_rate", "value": "0.60", "unit": "ratio", "description": "Discovery traffic to diner conversion rate", "approved": "TRUE"},
    
    # 3. INIT-AOV-001 params
    {"initiative_key": "INIT-AOV-001", "param_name": "delta_aov", "value": "1.5", "unit": "currency", "description": "Incremental AOV from upsell", "approved": "TRUE"},
    {"initiative_key": "INIT-AOV-001", "param_name": "monthly_transactions", "value": "2564400", "unit": "transactions/month", "description": "Total monthly transactions across all restaurants", "approved": "TRUE"},
    {"initiative_key": "INIT-AOV-001", "param_name": "net_adoption_rate", "value": "0.67", "unit": "ratio", "description": "Share of GMV processed through Qlub", "approved": "TRUE"},
    {"initiative_key": "INIT-AOV-001", "param_name": "monetization_rate", "value": "0.0185", "unit": "ratio", "description": "Qlub take rate on processed GMV", "approved": "TRUE"},
    
    # 4. INIT-MZ-001 params
    {"initiative_key": "INIT-MZ-001", "param_name": "base_processed_gmv", "value": "72179100", "unit": "currency/month", "description": "Current monthly Qlub processed GMV", "approved": "TRUE"},
    {"initiative_key": "INIT-MZ-001", "param_name": "monetization_rate_before", "value": "0.0185", "unit": "ratio", "description": "Current monetization rate (baseline)", "approved": "TRUE"},
    {"initiative_key": "INIT-MZ-001", "param_name": "monetization_rate_after", "value": "0.0200", "unit": "ratio", "description": "Expected monetization rate after dynamic pricing", "approved": "TRUE"},
    
    # 5. INIT-MP-003 params
    {"initiative_key": "INIT-MP-003", "param_name": "base_processed_gmv", "value": "72179100", "unit": "currency/month", "description": "Current monthly Qlub processed GMV", "approved": "TRUE"},
    {"initiative_key": "INIT-MP-003", "param_name": "fraud_rate_before", "value": "0.015", "unit": "ratio", "description": "Current fraud loss rate (baseline)", "approved": "TRUE"},
    {"initiative_key": "INIT-MP-003", "param_name": "fraud_rate_after", "value": "0.010", "unit": "ratio", "description": "Expected fraud loss rate after detection engine", "approved": "TRUE"},
    {"initiative_key": "INIT-MP-003", "param_name": "monetization_rate", "value": "0.0185", "unit": "ratio", "description": "Qlub take rate on recovered GMV", "approved": "TRUE"},
    
    # 6. INIT-RL-003 params
    {"initiative_key": "INIT-RL-003", "param_name": "existing_qlub_customer_base", "value": "400000", "unit": "users", "description": "Current Qlub customer base", "approved": "TRUE"},
    {"initiative_key": "INIT-RL-003", "param_name": "repeat_rate_before", "value": "0.30", "unit": "ratio", "description": "Current repeat rate (baseline)", "approved": "TRUE"},
    {"initiative_key": "INIT-RL-003", "param_name": "repeat_rate_after", "value": "0.34", "unit": "ratio", "description": "Expected repeat rate after push re-engagement", "approved": "TRUE"},
]

# ============================================================================
# OPTIMIZATION CENTER - Scenarios
# ============================================================================

SCENARIOS_ROWS = [
    {
        "scenario_name": "Q2_2026_Baseline",
        "period_key": "Q2_2026",
        "capacity_total_tokens": "3150",
        "objective_mode": "weighted_kpis",
        "objective_weights_json": json.dumps({
            "qlub_revenue": 0.4,
            "active_restaurants": 0.2,
            "net_adoption_rate": 0.15,
            "average_order_value": 0.1,
            "monthly_diners_channeled_via_qlub": 0.15,
        }),
        "notes": "Q2 2026 baseline scenario with weighted multi-KPI optimization",
    },
]

# ============================================================================
# OPTIMIZATION CENTER - Constraints
# ============================================================================

CONSTRAINTS_ROWS = [
    # Capacity cap (global)
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "capacity_cap",
        "dimension": "all",
        "dimension_key": "all",
        "min_tokens": "",
        "max_tokens": "3150",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "Global capacity cap for Q2 allocable tokens",
    },
    # Mandatory initiatives
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "mandatory",
        "dimension": "initiative",
        "dimension_key": "INIT-MP-001",
        "min_tokens": "",
        "max_tokens": "",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "Payment Compliance Upgrade is mandatory",
    },
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "mandatory",
        "dimension": "initiative",
        "dimension_key": "INIT-MP-002",
        "min_tokens": "",
        "max_tokens": "",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "System Reliability is mandatory",
    },
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "mandatory",
        "dimension": "initiative",
        "dimension_key": "INIT-MP-003",
        "min_tokens": "",
        "max_tokens": "",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "Fraud Detection is mandatory",
    },
    # Department capacity floors (minimum allocation per department)
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "capacity_floor",
        "dimension": "department",
        "dimension_key": "Tech",
        "min_tokens": "400",
        "max_tokens": "",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "Minimum Tech department allocation",
    },
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "constraint_type": "capacity_floor",
        "dimension": "department",
        "dimension_key": "Product",
        "min_tokens": "300",
        "max_tokens": "",
        "bundle_member_keys": "",
        "prereq_member_keys": "",
        "notes": "Minimum Product department allocation",
    },
]

# ============================================================================
# OPTIMIZATION CENTER - Targets (KPI floors with baselines)
# ============================================================================

TARGETS_ROWS = [
    # Revenue target with baseline
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "dimension": "all",
        "dimension_key": "all",
        "kpi_key": "qlub_revenue",
        "baseline_value": "1335313",  # Current monthly revenue
        "target_value": "1500000",    # Target monthly revenue
        "floor_or_goal": "floor",
        "notes": "Minimum revenue floor of 1.5M/month (currently at 1.335M)",
    },
    # Active restaurants target
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "dimension": "all",
        "dimension_key": "all",
        "kpi_key": "active_restaurants",
        "baseline_value": "1200",
        "target_value": "1250",
        "floor_or_goal": "floor",
        "notes": "Minimum 50 net new restaurants in Q2",
    },
    # Diners channeled target
    {
        "scenario_name": "Q2_2026_Baseline",
        "constraint_set_name": "default",
        "dimension": "all",
        "dimension_key": "all",
        "kpi_key": "monthly_diners_channeled_via_qlub",
        "baseline_value": "360000",
        "target_value": "420000",
        "floor_or_goal": "floor",
        "notes": "Target 60k incremental diners channeled per month",
    },
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_sheets_client() -> SheetsClient:
    """Get authenticated sheets client."""
    return SheetsClient(get_sheets_service())


def col_letter(n: int) -> str:
    """Convert 0-indexed column number to letter (0=A, 25=Z, 26=AA, etc.)."""
    result = ""
    while n >= 0:
        result = chr(n % 26 + ord('A')) + result
        n = n // 26 - 1
    return result


def write_data_only(
    client: SheetsClient,
    spreadsheet_id: str,
    tab: str,
    data_rows: list,
    num_cols: int,
    dry_run: bool = False,
) -> None:
    """Write ONLY data rows to a tab, starting at data_start_row().
    
    DOES NOT write headers - assumes headers and meta rows already exist.
    """
    tab_key = tab.strip().lower()
    d_row = data_start_row(tab_key)
    
    end_col = col_letter(num_cols - 1)
    
    if dry_run:
        print(f"    Data rows {d_row}-{d_row + len(data_rows) - 1} (cols A-{end_col})")
        return
    
    if data_rows:
        data_end_row = d_row + len(data_rows) - 1
        data_range = f"{tab}!A{d_row}:{end_col}{data_end_row}"
        client.update_values(
            spreadsheet_id=spreadsheet_id,
            range_=data_range,
            values=data_rows,
            value_input_option="USER_ENTERED",
        )


def populate_metrics_config(client: SheetsClient, dry_run: bool = False):
    """Populate Metrics_Config tab with KPI definitions.
    
    Column order (from Live Sheets Registry - 10 columns):
    A: kpi_key, B: kpi_name, C: kpi_level, D: unit, E: description,
    F: is_active, G: notes, H: run_status, I: updated_source, J: updated_at
    """
    print("\n📊 Populating Metrics_Config...")
    
    data_rows = []
    for row in METRICS_CONFIG_ROWS:
        data_rows.append([
            row["kpi_key"],           # A
            row["kpi_name"],          # B
            row["kpi_level"],         # C
            row["unit"],              # D
            row["description"],       # E
            row["is_active"],         # F
            row["notes"],             # G
            "",                       # H: run_status (backend writes)
            "",                       # I: updated_source (backend writes)
            "",                       # J: updated_at (backend writes)
        ])
    
    tab = PRODUCTOPS_CONFIG["metrics_config_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} KPI rows to {tab}")
    
    write_data_only(client, PRODUCTOPS_SHEET_ID, tab, data_rows, num_cols=10, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} KPI rows to {tab}")


def populate_central_backlog(client: SheetsClient, dry_run: bool = False):
    """Populate Central Backlog with all 25 initiatives.
    
    Column order (from Live Sheets Registry - 32 columns):
    A: Initiative Key, B: Title, C: Description, D: Department, E: Requesting Team,
    F: Requester Name, G: Requester Email, H: Country, I: Product Area, J: Lifecycle Status,
    K: Customer Segment, L: Initiative Type, M: Hypothesis, N: Problem Statement,
    O: Value Score, P: Effort Score, Q: Overall Score, R: Active Scoring Framework,
    S: Use Math Model, T: Dependencies Initiatives, U: Dependencies Others, V: LLM Summary,
    W: Strategic Priority Coefficient, X: Updated At, Y: Updated Source, Z: Immediate KPI Key,
    AA: Metric Chain JSON, AB: engineering_tokens, AC: deadline_date, AD: is_mandatory,
    AE: Is Optimization Candidate, AF: Candidate Period Key
    """
    print("\n📋 Populating Central Backlog...")
    
    sheet_id, tab = get_central_backlog_config()
    
    # Map of enriched initiatives (6) that should have MATH_MODEL framework
    enriched_keys = {m["initiative_key"] for m in MATHMODELS_ROWS}
    
    data_rows = []
    for init in ALL_INITIATIVES:
        is_enriched = init["initiative_key"] in enriched_keys
        data_rows.append([
            init["initiative_key"],                                           # A: Initiative Key
            init["title"],                                                    # B: Title
            init["description"],                                              # C: Description
            init["department"],                                               # D: Department
            "",                                                               # E: Requesting Team
            "",                                                               # F: Requester Name
            "",                                                               # G: Requester Email
            init["country"],                                                  # H: Country
            init["bucket"],                                                   # I: Product Area
            "new",                                                            # J: Lifecycle Status
            "",                                                               # K: Customer Segment
            "",                                                               # L: Initiative Type
            f"Testing hypothesis for {init['title']}" if is_enriched else "", # M: Hypothesis
            init["description"],                                              # N: Problem Statement
            "",                                                               # O: Value Score (backend)
            "",                                                               # P: Effort Score (backend)
            "",                                                               # Q: Overall Score (backend)
            "MATH_MODEL" if is_enriched else "",                              # R: Active Scoring Framework
            "TRUE" if is_enriched else "",                                    # S: Use Math Model
            "",                                                               # T: Dependencies Initiatives
            "",                                                               # U: Dependencies Others
            "",                                                               # V: LLM Summary
            "1.0",                                                            # W: Strategic Priority Coefficient
            "",                                                               # X: Updated At (backend)
            "",                                                               # Y: Updated Source (backend)
            init.get("immediate_kpi_key", ""),                                # Z: Immediate KPI Key
            "",                                                               # AA: Metric Chain JSON
            str(init.get("engineering_tokens", "")),                          # AB: engineering_tokens
            init.get("deadline", ""),                                         # AC: deadline_date
            "TRUE" if init.get("is_mandatory") else "",                       # AD: is_mandatory
            "TRUE",                                                           # AE: Is Optimization Candidate
            "Q2_2026",                                                        # AF: Candidate Period Key
        ])
    
    if dry_run:
        print(f"  Would write {len(data_rows)} initiatives to {tab}")
    
    write_data_only(client, sheet_id, tab, data_rows, num_cols=32, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} initiatives to {tab}")


def populate_mathmodels(client: SheetsClient, dry_run: bool = False):
    """Populate MathModels tab with enriched initiative formulas.
    
    Column order (from Live Sheets Registry - 19 columns):
    A: initiative_key, B: target KPI key, C: model_name, D: model_description_free_text,
    E: is_primary, F: metric_chain_text, G: immediate KPI key, H: computed_score,
    I: llm_suggested_metric_chain_text, J: formula_text, K: status, L: approved_by_user,
    M: llm_suggested_formula_text, N: llm_notes, O: assumptions_text, P: model_prompt_to_llm,
    Q: suggested_by_llm, R: updated source, S: updated at
    """
    print("\n🧮 Populating MathModels...")
    
    data_rows = []
    for row in MATHMODELS_ROWS:
        data_rows.append([
            row["initiative_key"],           # A: initiative_key
            row["target_kpi_key"],           # B: target KPI key
            row["model_name"],               # C: model_name
            "",                              # D: model_description_free_text
            row["is_primary"],               # E: is_primary
            row["metric_chain_text"],        # F: metric_chain_text
            row["immediate_kpi_key"],        # G: immediate KPI key
            "",                              # H: computed_score (backend)
            "",                              # I: llm_suggested_metric_chain_text
            row["formula_text"],             # J: formula_text
            "",                              # K: status
            row["approved_by_user"],         # L: approved_by_user
            "",                              # M: llm_suggested_formula_text
            "",                              # N: llm_notes
            row["assumptions_text"],         # O: assumptions_text
            "",                              # P: model_prompt_to_llm
            "",                              # Q: suggested_by_llm
            "",                              # R: updated source (backend)
            "",                              # S: updated at (backend)
        ])
    
    tab = PRODUCTOPS_CONFIG["mathmodels_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} math models to {tab}")
    
    write_data_only(client, PRODUCTOPS_SHEET_ID, tab, data_rows, num_cols=19, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} math models to {tab}")


def populate_params(client: SheetsClient, dry_run: bool = False):
    """Populate Params tab with parameter values for enriched initiatives.
    
    Column order (from Live Sheets Registry - 16 columns):
    A: initiative_key, B: framework, C: model name, D: param_name, E: value,
    F: approved, G: is_auto_seeded, H: param_display, I: description, J: unit,
    K: min, L: max, M: source, N: notes, O: updated source, P: updated at
    """
    print("\n⚙️ Populating Params...")
    
    data_rows = []
    for row in PARAMS_ROWS:
        data_rows.append([
            row["initiative_key"],        # A: initiative_key
            "MATH_MODEL",                 # B: framework
            "",                           # C: model name (optional)
            row["param_name"],            # D: param_name
            row["value"],                 # E: value
            row.get("approved", "TRUE"),  # F: approved
            "FALSE",                      # G: is_auto_seeded (manual entry)
            "",                           # H: param_display
            row.get("description", ""),   # I: description
            row.get("unit", ""),          # J: unit
            "",                           # K: min
            "",                           # L: max
            "",                           # M: source
            "",                           # N: notes
            "",                           # O: updated source (backend)
            "",                           # P: updated at (backend)
        ])
    
    tab = PRODUCTOPS_CONFIG["params_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} parameters to {tab}")
    
    write_data_only(client, PRODUCTOPS_SHEET_ID, tab, data_rows, num_cols=16, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} parameters to {tab}")


def populate_optimization_scenarios(client: SheetsClient, dry_run: bool = False):
    """Populate Optimization Center Scenario_Config tab.
    
    Column order (from Live Sheets Registry - 9 columns):
    A: scenario_name, B: period_key, C: capacity_total_tokens, D: objective_mode,
    E: objective_weights_json, F: notes, G: run_status, H: updated_source, I: updated_at
    """
    print("\n🎯 Populating Optimization Scenarios...")
    
    data_rows = []
    for row in SCENARIOS_ROWS:
        data_rows.append([
            row["scenario_name"],           # A: scenario_name
            row["period_key"],              # B: period_key
            row["capacity_total_tokens"],   # C: capacity_total_tokens
            row["objective_mode"],          # D: objective_mode
            row["objective_weights_json"],  # E: objective_weights_json
            row["notes"],                   # F: notes
            "",                             # G: run_status (backend)
            "",                             # H: updated_source (backend)
            "",                             # I: updated_at (backend)
        ])
    
    tab = OPTIMIZATION_CONFIG["scenario_config_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} scenarios to {tab}")
    
    write_data_only(client, OPTIMIZATION_SHEET_ID, tab, data_rows, num_cols=9, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} scenarios to {tab}")


def populate_optimization_constraints(client: SheetsClient, dry_run: bool = False):
    """Populate Optimization Center Constraints tab.
    
    Column order (from Live Sheets Registry - 13 columns):
    A: constraint_set_name, B: scenario_name, C: constraint_type, D: dimension,
    E: dimension_key, F: min_tokens, G: max_tokens, H: bundle_member_keys,
    I: prereq_member_keys, J: notes, K: run_status, L: updated_source, M: updated_at
    """
    print("\n🔒 Populating Optimization Constraints...")
    
    data_rows = []
    for row in CONSTRAINTS_ROWS:
        data_rows.append([
            row["constraint_set_name"],  # A: constraint_set_name
            row["scenario_name"],        # B: scenario_name
            row["constraint_type"],      # C: constraint_type
            row["dimension"],            # D: dimension
            row["dimension_key"],        # E: dimension_key
            row["min_tokens"],           # F: min_tokens
            row["max_tokens"],           # G: max_tokens
            row["bundle_member_keys"],   # H: bundle_member_keys
            row["prereq_member_keys"],   # I: prereq_member_keys
            row["notes"],                # J: notes
            "",                          # K: run_status (backend)
            "",                          # L: updated_source (backend)
            "",                          # M: updated_at (backend)
        ])
    
    tab = OPTIMIZATION_CONFIG["constraints_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} constraints to {tab}")
    
    write_data_only(client, OPTIMIZATION_SHEET_ID, tab, data_rows, num_cols=13, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} constraints to {tab}")


def populate_optimization_targets(client: SheetsClient, dry_run: bool = False):
    """Populate Optimization Center Targets tab.
    
    Column order (from Live Sheets Registry - 11 columns):
    A: constraint_set_name, B: scenario_name, C: dimension, D: dimension_key,
    E: kpi_key, F: floor_or_goal, G: target_value, H: notes,
    I: run_status, J: updated_source, K: updated_at
    
    NOTE: baseline_value is NOT in current sheet schema per registry.
    If needed, column must be added to sheet first.
    """
    print("\n🎯 Populating Optimization Targets...")
    
    data_rows = []
    for row in TARGETS_ROWS:
        data_rows.append([
            row["constraint_set_name"],  # A: constraint_set_name
            row["scenario_name"],        # B: scenario_name
            row["dimension"],            # C: dimension
            row["dimension_key"],        # D: dimension_key
            row["kpi_key"],              # E: kpi_key
            row["floor_or_goal"],        # F: floor_or_goal
            row["target_value"],         # G: target_value
            row["notes"],                # H: notes
            "",                          # I: run_status (backend)
            "",                          # J: updated_source (backend)
            "",                          # K: updated_at (backend)
        ])
    
    tab = OPTIMIZATION_CONFIG["targets_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} targets to {tab}")
    
    write_data_only(client, OPTIMIZATION_SHEET_ID, tab, data_rows, num_cols=11, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} targets to {tab}")


def populate_scoring_inputs(client: SheetsClient, dry_run: bool = False):
    """Populate Scoring_Inputs tab with initiative keys and framework settings.
    
    Column order (from Live Sheets Registry - 28 columns):
    A: initiative_key, B: updated at, C: active_scoring_framework, D: use_math_model,
    E: status, F: active_value_score, G: active_effort_score, H: active_overall_score,
    I: math_value_score, J: math_effort_score, K: math_overall_score, L: math_warnings,
    M: rice_reach, N: rice_impact, O: rice_confidence, P: rice_effort,
    Q: wsjf_business_value, R: wsjf_time_criticality, S: wsjf_risk_reduction, T: wsjf_job_size,
    U: rice_value_score, V: rice_effort_score, W: rice_overall_score,
    X: wsjf_value_score, Y: wsjf_effort_score, Z: wsjf_overall_score,
    AA: comment, AB: Updated Source
    """
    print("\n📝 Populating Scoring_Inputs...")
    
    # Map of enriched initiatives
    enriched_keys = {m["initiative_key"] for m in MATHMODELS_ROWS}
    
    data_rows = []
    for init in ALL_INITIATIVES:
        is_enriched = init["initiative_key"] in enriched_keys
        data_rows.append([
            init["initiative_key"],                    # A: initiative_key
            "",                                        # B: updated at (backend)
            "MATH_MODEL" if is_enriched else "",       # C: active_scoring_framework
            "TRUE" if is_enriched else "",             # D: use_math_model
            "",                                        # E: status
            "",                                        # F: active_value_score (backend)
            "",                                        # G: active_effort_score (backend)
            "",                                        # H: active_overall_score (backend)
            "",                                        # I: math_value_score (backend)
            "",                                        # J: math_effort_score (backend)
            "",                                        # K: math_overall_score (backend)
            "",                                        # L: math_warnings (backend)
            "",                                        # M: rice_reach
            "",                                        # N: rice_impact
            "",                                        # O: rice_confidence
            "",                                        # P: rice_effort
            "",                                        # Q: wsjf_business_value
            "",                                        # R: wsjf_time_criticality
            "",                                        # S: wsjf_risk_reduction
            "",                                        # T: wsjf_job_size
            "",                                        # U: rice_value_score (backend)
            "",                                        # V: rice_effort_score (backend)
            "",                                        # W: rice_overall_score (backend)
            "",                                        # X: wsjf_value_score (backend)
            "",                                        # Y: wsjf_effort_score (backend)
            "",                                        # Z: wsjf_overall_score (backend)
            "",                                        # AA: comment
            "",                                        # AB: Updated Source (backend)
        ])
    
    tab = PRODUCTOPS_CONFIG["scoring_inputs_tab"]
    
    if dry_run:
        print(f"  Would write {len(data_rows)} scoring input rows to {tab}")
    
    write_data_only(client, PRODUCTOPS_SHEET_ID, tab, data_rows, num_cols=28, dry_run=dry_run)
    
    if not dry_run:
        print(f"  ✅ Wrote {len(data_rows)} scoring input rows to {tab}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Q2 2026 Qlub Simulation - Sheet Population Script"
    )
    parser.add_argument("--all", action="store_true", help="Populate all sheets")
    parser.add_argument("--metrics-config", action="store_true", help="Populate Metrics_Config only")
    parser.add_argument("--backlog", action="store_true", help="Populate Central Backlog only")
    parser.add_argument("--mathmodels", action="store_true", help="Populate MathModels only")
    parser.add_argument("--params", action="store_true", help="Populate Params only")
    parser.add_argument("--scoring", action="store_true", help="Populate Scoring_Inputs only")
    parser.add_argument("--optimization", action="store_true", help="Populate Optimization Center only")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing")
    
    args = parser.parse_args()
    
    # Default to --all if no specific flags
    if not any([args.all, args.metrics_config, args.backlog, args.mathmodels, 
                args.params, args.scoring, args.optimization]):
        args.all = True
    
    print("=" * 60)
    print("🚀 Q2 2026 Qlub Simulation - Sheet Population")
    print("=" * 60)
    print(f"\nProductOps Sheet ID: {PRODUCTOPS_SHEET_ID}")
    print(f"Optimization Sheet ID: {OPTIMIZATION_SHEET_ID}")
    
    backlog_id, backlog_tab = get_central_backlog_config()
    print(f"Central Backlog: {backlog_id} / {backlog_tab}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
    
    client = get_sheets_client()
    
    if args.all or args.metrics_config:
        populate_metrics_config(client, args.dry_run)
    
    if args.all or args.backlog:
        populate_central_backlog(client, args.dry_run)
    
    if args.all or args.mathmodels:
        populate_mathmodels(client, args.dry_run)
    
    if args.all or args.params:
        populate_params(client, args.dry_run)
    
    if args.all or args.scoring:
        populate_scoring_inputs(client, args.dry_run)
    
    if args.all or args.optimization:
        populate_optimization_scenarios(client, args.dry_run)
        populate_optimization_constraints(client, args.dry_run)
        populate_optimization_targets(client, args.dry_run)
    
    print("\n" + "=" * 60)
    print("✅ Population complete!")
    print("=" * 60)
    print("\n📌 Next steps:")
    print("   1. Open ProductOps sheet and run 'Seed Math Params' for MathModels")
    print("   2. Open Scoring_Inputs and run 'Score Selected' for enriched initiatives")
    print("   3. Check KPI_Contributions tab for computed contributions")
    print("   4. Open Optimization Center and run optimization")


if __name__ == "__main__":
    main()
