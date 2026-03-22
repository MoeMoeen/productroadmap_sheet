Perfect. We’ll do it one step at a time.

You’re aligned with the workflow. The key mechanics are indeed:

* `Metrics_Config` defines the canonical KPI universe used everywhere else. `kpi_key` values are later referenced by `MathModels.target_kpi_key`, Optimization Targets, and scenario objective weights. Also, north-star mode requires exactly one active `north_star` KPI. 
* In `MathModels`, PM creates the initiative-level formula model, including `target_kpi_key`, optional `immediate KPI key`, `metric_chain_text`, `formula_text`, and approval. Only one primary model per initiative should be marked true. 
* Then `pm.seed_math_params` extracts variables from approved formulas into `Params`; after PM fills parameter values and saves them, `pm.score_selected` computes the score.
* KPI contributions are auto-computed only when scoring runs with the `MATH_MODEL` framework, then written to `KPI_Contributions`. PM can override there if needed.

So the correct first move is:

# Step 3A — define the Qlub KPI registry in `Metrics_Config`

Below is the exact first draft I recommend for your Q2 2026 simulation.

## Proposed `Metrics_Config` rows

| kpi_key                             | kpi_name                          |  kpi_level | unit               | description                                                                                                            | is_active | notes                                         |
| ----------------------------------- | --------------------------------- | ---------: | ------------------ | ---------------------------------------------------------------------------------------------------------------------- | --------: | --------------------------------------------- |
| `qlub_revenue`                      | Qlub Revenue                      | north_star | currency_per_month | Revenue captured by Qlub from processed GMV times monetization rate.                                                   |      TRUE | Single active north star for this simulation. |
| `active_restaurants`                | Active Restaurants                |  strategic | count              | Number of active restaurants live on Qlub in the period.                                                               |      TRUE | Strategic growth KPI.                         |
| `net_adoption_rate`                 | Net Adoption Rate                 |  strategic | ratio              | Share of total restaurant GMV effectively processed through Qlub after gross adoption and checkout completion effects. |      TRUE | Strategic product-usage KPI.                  |
| `average_order_value`               | Average Order Value               |  strategic | currency_per_order | Average value of a restaurant transaction/order.                                                                       |      TRUE | Strategic economics KPI.                      |
| `monthly_diners_channeled_via_qlub` | Monthly Diners Channeled via Qlub |  strategic | diners_per_month   | Actual diners/customers channeled to restaurants through Qlub discovery or demand-generation mechanisms.               |      TRUE | Strategic traffic-generation KPI.             |

## Important note

For this first simulation, I recommend that `Metrics_Config` contain only:

* 1 north star
* 4 strategic KPIs

and **not** all supporting metrics yet.

Why: your sheet instructions say `Metrics_Config` is for org KPIs, specifically north star and strategic metrics. 
Supporting metrics like `checkout_completion_rate`, `qlub_discovery_traffic`, or `gross_adoption_rate` can still appear inside `MathModels.metric_chain_text`, `formula_text`, and `immediate KPI key` without necessarily being organization-level KPIs.

That keeps the KPI universe clean and avoids polluting optimization with low-level operational metrics too early.

