# app/schemas/feasibility.py
"""
Feasibility report schemas for pre-solver validation.
Used to detect hard contradictions and capacity impossibilities before calling the solver.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["error", "warning"]


class FeasibilityIssue(BaseModel):
    """A single feasibility issue (error or warning)."""
    model_config = ConfigDict(extra="ignore")

    severity: Severity
    code: str
    message: str

    # Optional fields for structured UI feedback / debugging
    initiative_keys: List[str] = Field(default_factory=list)
    dimension: Optional[str] = None
    dimension_key: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class FeasibilityReport(BaseModel):
    """
    Structured feasibility check report.
    Used to communicate pre-solver validation results to UI/API/workers.
    """
    model_config = ConfigDict(extra="ignore")

    is_feasible: bool
    errors: List[FeasibilityIssue] = Field(default_factory=list)
    warnings: List[FeasibilityIssue] = Field(default_factory=list)
    summary: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_issues(cls, issues: List[FeasibilityIssue]) -> "FeasibilityReport":
        """Build a report from a list of issues, auto-calculating feasibility status."""
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        is_feasible = len(errors) == 0
        summary = (
            f"feasible ({len(warnings)} warnings)" if is_feasible else f"infeasible ({len(errors)} errors, {len(warnings)} warnings)"
        )
        return cls(is_feasible=is_feasible, errors=errors, warnings=warnings, summary=summary)
