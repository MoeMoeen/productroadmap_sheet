# app/schemas/optimization_solution.py
"""
Optimization solution schemas for solver output.

Represents the structured result from solver (OR-Tools CP-SAT, etc.).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal


SolveStatus = Literal["optimal", "feasible", "infeasible", "model_invalid", "unknown"]


class SelectedItem(BaseModel):
    """A single candidate's selection status and allocated resources."""
    
    model_config = ConfigDict(extra="ignore")

    initiative_key: str
    selected: bool
    allocated_tokens: Optional[float] = None  # v1: equals engineering_tokens when selected
    rank: Optional[int] = None  # fill later if you want


class OptimizationSolution(BaseModel):
    """
    Structured solver output.
    
    Contains:
    - Status (optimal, feasible, infeasible, etc.)
    - Selected initiatives with allocations
    - Objective value (when objective is implemented)
    - Capacity usage
    - Diagnostics for debugging
    """
    
    model_config = ConfigDict(extra="ignore")

    status: SolveStatus
    selected: List[SelectedItem] = Field(default_factory=list)

    objective_value: Optional[float] = None  # filled when objective implemented
    capacity_used_tokens: Optional[float] = None

    # Useful diagnostics
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
