# Phase 4 - Sheet Schemas Reference

## MathModels Tab - Column Specification

| Column Name                   | Type    | Editable By | Required | Notes                                    |
|-------------------------------|---------|-------------|----------|------------------------------------------|
| initiative_key                | string  | Backend     | Yes      | Primary key, read-only                   |
| framework                     | string  | Backend     | Yes      | Always "MATH_MODEL" in v1                |
| model_name                    | string  | PM          | No       | Short friendly name                      |
| model_description_free_text   | text    | PM          | No       | Natural language description             |
| model_prompt_to_llm           | text    | PM          | No       | Optional LLM steering                    |
| llm_suggested_formula_text    | text    | LLM         | No       | Auto-generated, PM reads only            |
| assumptions_text              | text    | LLM+PM      | No       | LLM seeds, PM edits                      |
| llm_notes                     | text    | LLM+PM      | No       | LLM explanation/commentary               |
| formula_text_final            | text    | PM          | No       | **Canonical formula for scoring**        |
| formula_text_approved         | boolean | PM          | No       | Gatekeeper flag                          |

---

## Params Tab - Column Specification

| Column Name     | Type    | Editable By           | Required | Notes                              |
|-----------------|---------|----------------------|----------|------------------------------------|
| initiative_key  | string  | Backend              | Yes      | Links to initiative                |
| framework       | string  | Backend              | Yes      | e.g., MATH_MODEL, RICE, WSJF       |
| param_name      | string  | Backend (auto-seed)  | Yes      | Internal identifier (snake_case)   |
| param_display   | string  | LLM+PM               | No       | Human-friendly label               |
| description     | text    | LLM+PM               | No       | What this parameter means          |
| value           | number  | PM/Analytics/Finance | No       | **Actual numeric value**           |
| unit            | string  | LLM+PM               | No       | %, £, sessions, days, etc.         |
| min             | number  | LLM+PM               | No       | Lower bound (optional)             |
| max             | number  | LLM+PM               | No       | Upper bound (optional)             |
| source          | string  | LLM+PM               | No       | PM, Analytics, Finance, Eng        |
| approved        | boolean | PM/owner             | No       | Must be TRUE for scoring           |
| is_auto_seeded  | boolean | Backend              | Yes      | Distinguishes auto vs manual       |
| notes           | text    | All                  | No       | Free-form comments                 |

---

## Scoring_Inputs Tab - NEW Columns for Phase 4

**Add these columns to existing Scoring_Inputs tab:**

| Column Name         | Type  | Notes                                    |
|---------------------|-------|------------------------------------------|
| math_value_score    | float | Backend writes, PM reads                 |
| math_effort_score   | float | Backend writes, PM reads                 |
| math_overall_score  | float | Backend writes, PM reads                 |

These sit alongside existing `rice_*_score` and `wsjf_*_score` columns.

---

## Column Ordering Guidelines (ProductOps Scoring Tab)

Recommended left-to-right order for clarity:

1. **Identity & Control** (2-3 cols):
   - `initiative_key`
   - `active_scoring_framework` (dropdown)
   - `use_math_model` (checkbox)

2. **RICE Framework** (3 cols):
   - `rice_value_score`
   - `rice_effort_score`
   - `rice_overall_score`

3. **WSJF Framework** (3 cols):
   - `wsjf_value_score`
   - `wsjf_effort_score`
   - `wsjf_overall_score`

4. **MATH_MODEL Framework** (3 cols):
   - `math_value_score`
   - `math_effort_score`
   - `math_overall_score`

This makes it easy to scan and compare frameworks side-by-side.

---

## Data Type Specifications (for Sheet Validation)

### MathModels Tab

- **Text columns** (allow line breaks):
  - `model_description_free_text` (max ~500 chars)
  - `model_prompt_to_llm` (max ~500 chars)
  - `llm_suggested_formula_text` (max ~2000 chars; 10 lines max per requirement)
  - `assumptions_text` (max ~1000 chars)
  - `llm_notes` (max ~1000 chars)
  - `formula_text_final` (max ~2000 chars; 10 lines max per requirement)

- **Checkbox columns** (TRUE/FALSE):
  - `formula_text_approved`

- **Read-only columns** (grey out in UI):
  - `initiative_key`
  - `framework`

### Params Tab

- **Number columns**:
  - `value` (decimal, 2 decimal places for currency; otherwise as needed)
  - `min`, `max` (decimal, match value precision)

- **Text columns**:
  - `param_display` (max ~100 chars)
  - `description` (max ~500 chars)
  - `unit` (max ~50 chars; e.g. "%", "£", "sessions")
  - `source` (dropdown: "PM", "Analytics", "Finance", "Eng", "LLM")
  - `notes` (max ~500 chars)

- **Checkbox columns**:
  - `approved`
  - `is_auto_seeded`

- **Read-only columns**:
  - `initiative_key`
  - `framework`
  - `param_name`
  - `is_auto_seeded`

---

## Notes on Editability

**MathModels Tab:**
- PM should have **write access** to all columns except:
  - `initiative_key` (backend)
  - `framework` (backend)
  - `llm_suggested_formula_text` (LLM only)

**Params Tab:**
- PM/Analytics/Finance should have **write access** to all columns except:
  - `initiative_key` (backend)
  - `framework` (backend)
  - `param_name` (backend for auto-seeded)
  - `is_auto_seeded` (backend)

**Scoring Tab:**
- PM should have **write access** to:
  - `active_scoring_framework` (choice critical for Flow 2)
  - `use_math_model` (checkbox)
- All `*_score` columns should be **read-only** (backend-written via Flow 3)