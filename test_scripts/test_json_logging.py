#!/usr/bin/env python3
"""Test script to verify JSON logging configuration works correctly."""

import logging
from app.config import settings

# Get the logger from app config
logger = logging.getLogger("app.test")

def test_basic_logging():
    """Test basic logging without extra fields."""
    logger.info("Basic log message without extra fields")
    logger.warning("Warning message")
    logger.error("Error message")

def test_logging_with_extra():
    """Test logging with extra fields (common in scoring)."""
    logger.info(
        "scoring.batch_start",
        extra={
            "framework": "RICE",
            "total": 100,
            "initiative_key": "INIT-001"
        }
    )
    
    logger.debug(
        "scoring.computed",
        extra={
            "initiative_key": "INIT-002",
            "framework": "WSJF",
            "overall_score": 42.5,
            "value_score": 100.0,
            "effort_score": 2.35
        }
    )
    
    logger.warning(
        "scoring.warning",
        extra={
            "initiative_key": "INIT-003",
            "framework": "MATH_MODEL",
            "warning": "Missing params: x, y"
        }
    )

def test_partial_fields():
    """Test with only some fields present."""
    logger.info(
        "flow3.sync.done",
        extra={
            "updated": 50,
            "rows": 100
        }
    )

def main():
    print("=" * 80)
    print("Testing JSON Logging Configuration")
    print("=" * 80)
    print()
    
    print("1. Basic logging (no extra fields):")
    print("-" * 40)
    test_basic_logging()
    print()
    
    print("2. Logging with extra fields (scoring context):")
    print("-" * 40)
    test_logging_with_extra()
    print()
    
    print("3. Logging with partial fields:")
    print("-" * 40)
    test_partial_fields()
    print()
    
    print("=" * 80)
    print("JSON logging test complete!")
    print("Each log line above should be valid JSON with only relevant fields.")
    print("=" * 80)

if __name__ == "__main__":
    # Set to DEBUG to see all logs
    logging.getLogger("app").setLevel(logging.DEBUG)
    main()
