# Framework Parameter Naming Convention

## Unified Naming: `<framework>_<parameter>`

All framework-specific scoring parameters follow a consistent naming convention **across all three layers**:

### Layer 1: Google Sheets Column Headers
Use direct snake_case with framework prefix:
```
rice_reach
rice_impact
rice_confidence
rice_effort
wsjf_business_value
wsjf_time_criticality
wsjf_risk_reduction
wsjf_job_size
```

**Note**: The reader also supports the legacy namespaced format (`RICE: Reach`, `WSJF: Job Size`) for backwards compatibility.

### Layer 2: Python Code (Reader Output)
Same names as sheet headers (no transformation needed):
```python
rice_reach
rice_impact
rice_confidence
rice_effort
wsjf_business_value
wsjf_time_criticality
wsjf_risk_reduction
wsjf_job_size
```

### Layer 3: Database Columns
Initiative model fields use exact same names:
```python
class Initiative(Base):
    # RICE framework parameters
    rice_reach = Column(Float, nullable=True)
    rice_impact = Column(Float, nullable=True)
    rice_confidence = Column(Float, nullable=True)
    rice_effort = Column(Float, nullable=True)
    
    # WSJF framework parameters
    wsjf_business_value = Column(Float, nullable=True)
    wsjf_time_criticality = Column(Float, nullable=True)
    wsjf_risk_reduction = Column(Float, nullable=True)
    wsjf_job_size = Column(Float, nullable=True)
```

## Benefits

1. **Self-documenting**: Parameter name clearly indicates which framework it belongs to
2. **Namespace isolation**: No collision between frameworks (e.g., RICE impact vs WSJF business value)
3. **Traceability**: Same name flows through sheet → code → database
4. **Extensibility**: Easy to add new frameworks (e.g., `kano_satisfaction`, `math_model_1_x`)

## Shared Parameters

Some parameters are framework-agnostic and don't need prefixes:
- `effort_engineering_days` (used as fallback/compatibility; can be populated from `rice_effort` or `wsjf_job_size`)
- `strategic_priority_coefficient`
- `risk_level`
- `time_sensitivity`

## Migration Path

### New fields (v2 - current):
- `rice_reach`, `rice_impact`, `rice_confidence`, `rice_effort`
- `wsjf_business_value`, `wsjf_time_criticality`, `wsjf_risk_reduction`, `wsjf_job_size`

### Deprecated fields (v1 - for backwards compatibility):
- `reach_estimated_users` (use `rice_reach`)
- `impact_expected` (use `rice_impact`)

## Example Sheet Structure

Your Product Ops `Scoring_Inputs` tab should have:

| initiative_key | rice_reach | rice_impact | rice_confidence | rice_effort | wsjf_business_value | wsjf_time_criticality | wsjf_risk_reduction | wsjf_job_size | active_scoring_framework | strategic_priority_coefficient |
|---------------|------------|-------------|-----------------|-------------|--------------------|-----------------------|--------------------|---------------|--------------------------|-------------------------------|
| INIT-001      | 1000       | 2.5         | 0.8             | 5           | 7.5                | 4                     | 3                  | 5             | RICE                     | 1.5                           |
| INIT-002      |            |             |                 |             | 10                 | 5                     | 4                  | 8             | WSJF                     | 2.0                           |

**Legacy format also supported** (for backwards compatibility):
| Initiative Key | RICE: Reach | RICE: Impact | ... |
|---------------|-------------|--------------|-----|

## Code Usage

### Reading in ScoringService:
```python
# RICE
reach = initiative.rice_reach or settings.SCORING_DEFAULT_RICE_REACH
impact = initiative.rice_impact or settings.SCORING_DEFAULT_RICE_IMPACT
confidence = initiative.rice_confidence or settings.SCORING_DEFAULT_RICE_CONFIDENCE
effort = initiative.rice_effort or settings.SCORING_DEFAULT_RICE_EFFORT

# WSJF
business_value = initiative.wsjf_business_value or default
time_criticality = initiative.wsjf_time_criticality or default
risk_reduction = initiative.wsjf_risk_reduction or default
job_size = initiative.wsjf_job_size or default
```

### Writing in Flow3 Sync:
```python
# Direct mapping from sheet → DB (unified naming)
ini.rice_reach = row.framework_inputs["RICE"]["rice_reach"]
ini.wsjf_job_size = row.framework_inputs["WSJF"]["wsjf_job_size"]
```
