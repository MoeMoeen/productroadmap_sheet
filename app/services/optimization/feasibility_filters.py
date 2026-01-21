# app/services/feasibility_filters.py
"""
Pre-solver feasibility filters for candidate initiatives.
Phase 5 rule: Time-related constraints (deadlines, earliest_start, etc.) 
must be applied BEFORE building OptimizationProblem.candidates.
"""
from __future__ import annotations

from datetime import date

from app.db.models.initiative import Initiative


def is_deadline_feasible(initiative: Initiative, period_end: date) -> bool:
    """
    Check if an initiative's deadline is feasible for a given period.
    
    Phase 5 rule: If initiative.deadline_date > period_end, the initiative
    cannot meet its deadline within the period and must be excluded from
    the candidate pool BEFORE solver runs.
    
    Args:
        initiative: Initiative to check
        period_end: End date of the optimization period (inclusive)
        
    Returns:
        True if deadline is feasible (or no deadline set), False otherwise
    """
    # PRODUCTION FIX: Treat None deadline as "no constraint" (always feasible)
    if initiative.deadline_date is None:
        return True
    
    # PRODUCTION FIX: Handle timezone-naive dates consistently
    # SQLAlchemy Date columns return date objects (not datetime), so comparison is safe
    # type: ignore suppresses false positive - at runtime this returns bool
    return bool(initiative.deadline_date <= period_end)  # type: ignore[return-value]


def is_time_feasible(
    initiative: Initiative,
    period_start: date,
    period_end: date,
) -> bool:
    """
    Extended time feasibility check (for future phases).
    Currently only checks deadline, but can be extended to check:
    - earliest_start_date (if initiative cannot start until after period ends)
    - latest_finish_date (if initiative must finish before period starts)
    
    Args:
        initiative: Initiative to check
        period_start: Start date of the optimization period (inclusive)
        period_end: End date of the optimization period (inclusive)
        
    Returns:
        True if initiative is time-feasible for the period, False otherwise
    """
    # PRODUCTION FIX: Placeholder for future time constraints
    # Phase 5: Only deadline is enforced
    
    # Check deadline feasibility
    if not is_deadline_feasible(initiative, period_end):
        return False
    
    # Future TODO: Check earliest_start_date
    # if initiative.earliest_start_date and initiative.earliest_start_date > period_end:
    #     return False
    
    # Future TODO: Check latest_finish_date
    # if initiative.latest_finish_date and initiative.latest_finish_date < period_start:
    #     return False
    
    return True
