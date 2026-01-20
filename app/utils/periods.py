# app/utils/periods.py
"""
Period parsing utilities for optimization scenarios.
Supports quarterly, monthly, and weekly period formats.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re


@dataclass(frozen=True)
class PeriodWindow:
    """
    Represents a time period with start and end dates (end is inclusive).
    Used for deadline feasibility filtering and time-based constraints.
    """
    start: date
    end: date  # inclusive

    def contains(self, dt: date) -> bool:
        """Check if a date falls within this period (inclusive)."""
        return self.start <= dt <= self.end


def parse_period_key(period_key: str) -> PeriodWindow:
    """
    Parse a period key string into a PeriodWindow.
    
    Supported formats:
    - Quarterly: "YYYY-QN" (e.g., "2026-Q1", "2026-Q4")
    - Monthly: "YYYY-MN" or "YYYY-MM" (e.g., "2026-M3", "2026-03")
    - Weekly: "YYYY-WN" or "YYYY-WNN" (e.g., "2026-W5", "2026-W52")
    
    Args:
        period_key: Period identifier string
        
    Returns:
        PeriodWindow with start and end dates (inclusive)
        
    Raises:
        ValueError: If period_key format is not recognized or invalid
    """
    # PRODUCTION FIX: Robust period parsing with clear error messages
    if not period_key or not isinstance(period_key, str):
        raise ValueError(f"Invalid period_key: must be a non-empty string, got {period_key!r}")
    
    period_key = period_key.strip().upper()
    
    # Quarterly format: YYYY-QN
    quarterly_match = re.match(r"^(\d{4})-Q([1-4])$", period_key)
    if quarterly_match:
        year = int(quarterly_match.group(1))
        quarter = int(quarterly_match.group(2))
        return _parse_quarterly(year, quarter)
    
    # Monthly format: YYYY-MN or YYYY-MM (M1-M12 or 01-12)
    monthly_match = re.match(r"^(\d{4})-M?(\d{1,2})$", period_key)
    if monthly_match:
        year = int(monthly_match.group(1))
        month = int(monthly_match.group(2))
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month in period_key '{period_key}': month must be 1-12")
        return _parse_monthly(year, month)
    
    # Weekly format: YYYY-WN or YYYY-WNN (W1-W53)
    weekly_match = re.match(r"^(\d{4})-W(\d{1,2})$", period_key)
    if weekly_match:
        year = int(weekly_match.group(1))
        week = int(weekly_match.group(2))
        if week < 1 or week > 53:
            raise ValueError(f"Invalid week in period_key '{period_key}': week must be 1-53")
        return _parse_weekly(year, week)
    
    # PRODUCTION FIX: Clear error message with supported formats
    raise ValueError(
        f"Unrecognized period_key format: '{period_key}'. "
        f"Supported formats: 'YYYY-QN' (quarters), 'YYYY-MN' (months), 'YYYY-WN' (weeks). "
        f"Examples: '2026-Q1', '2026-M3', '2026-03', '2026-W5'"
    )


def _parse_quarterly(year: int, quarter: int) -> PeriodWindow:
    """Parse quarterly period (Q1-Q4)."""
    # PRODUCTION FIX: Validate year range to prevent date overflow
    if year < 1900 or year > 2100:
        raise ValueError(f"Invalid year {year}: must be between 1900 and 2100")
    
    # Quarter start months: Q1=Jan, Q2=Apr, Q3=Jul, Q4=Oct
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    
    # Calculate end month (last month of quarter)
    end_month = start_month + 2
    if end_month > 12:
        # Q4 ends in December
        end_month = 12
    
    # Last day of end month
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        # Get first day of next month, then subtract 1 day
        next_month_start = date(year, end_month + 1, 1)
        end = next_month_start - timedelta(days=1)
    
    return PeriodWindow(start=start, end=end)


def _parse_monthly(year: int, month: int) -> PeriodWindow:
    """Parse monthly period (1-12)."""
    # PRODUCTION FIX: Validate year range
    if year < 1900 or year > 2100:
        raise ValueError(f"Invalid year {year}: must be between 1900 and 2100")
    
    start = date(year, month, 1)
    
    # Calculate last day of month
    if month == 12:
        # December ends on 31st
        end = date(year, 12, 31)
    else:
        # Get first day of next month, then subtract 1 day
        next_month_start = date(year, month + 1, 1)
        end = next_month_start - timedelta(days=1)
    
    return PeriodWindow(start=start, end=end)


def _parse_weekly(year: int, week: int) -> PeriodWindow:
    """
    Parse weekly period (ISO week numbering).
    Week 1 starts on the first Monday of the year (ISO 8601).
    """
    # PRODUCTION FIX: Validate year range
    if year < 1900 or year > 2100:
        raise ValueError(f"Invalid year {year}: must be between 1900 and 2100")
    
    # Find first Monday of the year (start of week 1)
    jan_1 = date(year, 1, 1)
    # Monday is weekday 0, Sunday is 6
    days_to_monday = (7 - jan_1.weekday()) % 7
    if days_to_monday == 0 and jan_1.weekday() != 0:
        # If Jan 1 is not Monday, find next Monday
        days_to_monday = 7 - jan_1.weekday()
    
    week_1_start = jan_1 + timedelta(days=days_to_monday)
    
    # Calculate this week's start
    start = week_1_start + timedelta(weeks=week - 1)
    end = start + timedelta(days=6)  # Sunday (inclusive)
    
    return PeriodWindow(start=start, end=end)


def get_period_end_date(period_key: str) -> date:
    """
    Convenience function to extract just the end date from a period key.
    Used for deadline feasibility checks.
    """
    return parse_period_key(period_key).end
