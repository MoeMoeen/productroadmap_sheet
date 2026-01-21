# productroadmap_sheet_project/app/services/scoring/utils.py

from __future__ import annotations

from typing import Optional, Tuple


def safe_div(numerator: Optional[float], denominator: Optional[float]) -> Tuple[float, Optional[str]]:
    """Safely divide two optional floats.

    Returns (result, warning). If denominator is <= 0 or None, result=0.0 and a warning
    is returned. If numerator is None, it is treated as 0 with a warning.
    """
    if denominator is None or denominator <= 0:
        return 0.0, "Denominator missing or non-positive; returning 0."
    if numerator is None:
        return 0.0, "Numerator missing; treated as 0."
    return numerator / denominator, None


def clamp(value: Optional[float], min_value: float, max_value: float) -> float:
    """Clamp a possibly None float into [min_value, max_value]. None -> min_value."""
    if value is None:
        return min_value
    return max(min_value, min(max_value, value))


__all__ = ["safe_div", "clamp"]
