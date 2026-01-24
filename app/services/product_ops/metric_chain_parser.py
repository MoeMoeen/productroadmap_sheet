# productroadmap_sheet_project/app/services/product_ops/metric_chain_parser.py
"""
Metric Chain Parser (Token Extractor)

Extracts metric identifiers from PM input text. This is NOT a semantic parser -
it's a token extractor that splits on arrows/operators and extracts alphanumeric identifiers.

Input formats supported:
- "signup → activation → revenue"
- "signup -> activation -> revenue"  
- "traffic * conversion = revenue" (extracts: traffic, conversion, revenue)
- "MAU → DAU → engagement → retention"

Note: For "traffic * conversion = revenue", parser extracts ["traffic", "conversion", "revenue"]
without understanding the equation semantics. This is sufficient for KPI identification.

Output:
{
    "chain": ["signup", "activation", "revenue"],
    "validated": True,  # All keys found in OrganizationMetricConfig
    "invalid_keys": [],  # KPI keys not found
    "source": "pm_input"
}

Used by:
- Flow 3 ProductOps sync (parse Initiative.metric_chain_text)
- LLM prompts (inject context for math model generation)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.db.models.optimization import OrganizationMetricConfig

logger = logging.getLogger(__name__)


def parse_metric_chain(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Parse metric chain text into structured JSON.
    
    Args:
        text: Metric chain string (e.g., "signup → activation → revenue")
    
    Returns:
        {
            "chain": ["signup", "activation", "revenue"],
            "raw": "signup → activation → revenue",
            "source": "pm_input"
        }
        Returns None if text is None/empty
    """
    if not text or not str(text).strip():
        return None
    
    text = str(text).strip()
    
    # Normalize arrows and operators
    # Replace various arrow types: →, ->, =>, ⇒
    normalized = text
    normalized = re.sub(r'[→⇒]', '->', normalized)
    normalized = re.sub(r'=>', '->', normalized)
    
    # Split by arrows or operators (*,  /, +, =)
    # Keep only alphanumeric and underscores for metric keys
    separators = r'->|\*|/|\+|='
    parts = re.split(separators, normalized)
    
    # Clean and extract metric keys
    chain = []
    for part in parts:
        # Remove whitespace and special chars, keep only valid key characters
        cleaned = part.strip()
        # Extract valid metric key (alphanumeric, underscore, hyphen)
        match = re.search(r'[a-zA-Z][a-zA-Z0-9_\-]*', cleaned)
        if match:
            key = match.group(0).lower()
            if key:
                chain.append(key)
    
    if not chain:
        return None
    
    return {
        "chain": chain,
        "raw": text,
        "source": "pm_input",
    }


def validate_metric_chain(
    db: Session,
    metric_chain_json: Dict[str, Any],
    kpi_levels: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validate metric chain keys against OrganizationMetricConfig.
    
    Validation rules:
    1. All nodes must exist in OrganizationMetricConfig and be active
    2. Chain must have at least 1 node
    3. If kpi_levels specified, the LAST node must be in those levels (not all nodes)
       - Allows intermediate operational/driver metrics in the chain
       - Enforces that chain ends in strategic/north_star (output KPIs for optimization)
    
    Args:
        db: Database session
        metric_chain_json: Parsed metric chain dict with "chain" field
        kpi_levels: Optional filter for TAIL node KPI levels (e.g., ["north_star", "strategic"])
                   If provided, validates that the last node is in one of these levels.
                   Intermediate nodes can be any active KPI level.
    
    Returns:
        {
            "chain": ["signup", "activation", "revenue"],
            "validated": True,
            "invalid_keys": [],
            "valid_keys": ["signup", "activation", "revenue"],
            "tail_level_valid": True,  # If kpi_levels specified, tail in allowed levels
            "tail_kpi_level": "strategic",  # Level of the last node
            "all_allowed_keys": [all_kpi_keys_from_config]
        }
    """
    if not metric_chain_json or "chain" not in metric_chain_json:
        return {
            "chain": [],
            "validated": False,
            "invalid_keys": [],
            "valid_keys": [],
            "all_allowed_keys": [],
            "tail_level_valid": None,
            "tail_kpi_level": None,
        }
    
    chain = metric_chain_json["chain"]
    
    # Load ALL active KPI keys (any level) for node existence validation
    configs = db.query(OrganizationMetricConfig).all()
    all_active_keys: Set[str] = set()
    kpi_level_map: Dict[str, str] = {}  # key -> level mapping
    
    for cfg in configs:
        meta = cfg.metadata_json or {}
        is_active = meta.get("is_active", True)
        
        if not is_active:
            continue
        
        if cfg.kpi_key is not None:
            key_lower = cfg.kpi_key.lower()
            all_active_keys.add(key_lower)
            level_val = cfg.kpi_level
            kpi_level_map[key_lower] = str(level_val) if level_val is not None else "unknown"
    
    # Validate each key exists in registry (any level)
    valid_keys = [k for k in chain if k.lower() in all_active_keys]
    invalid_keys = [k for k in chain if k.lower() not in all_active_keys]
    
    # Validate tail node level if kpi_levels specified
    tail_level_valid = None
    tail_kpi_level = None
    
    if kpi_levels and chain:
        tail_key = chain[-1].lower()
        tail_kpi_level = kpi_level_map.get(tail_key)
        tail_level_valid = tail_kpi_level in kpi_levels if tail_kpi_level else False
    
    # Overall validation: no invalid keys + (tail level valid if required)
    validated = len(invalid_keys) == 0
    if kpi_levels and tail_level_valid is not None:
        validated = validated and tail_level_valid
    
    return {
        "chain": chain,
        "validated": validated,
        "invalid_keys": invalid_keys,
        "valid_keys": valid_keys,
        "tail_level_valid": tail_level_valid,
        "tail_kpi_level": tail_kpi_level,
        "all_allowed_keys": sorted(list(all_active_keys)),
        "raw": metric_chain_json.get("raw"),
        "source": metric_chain_json.get("source", "pm_input"),
    }


def parse_and_validate(
    db: Session,
    text: Optional[str],
    kpi_levels: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Parse and validate metric chain in one step.
    
    Convenience method combining parse_metric_chain() and validate_metric_chain().
    
    Returns validated dict or None if text is empty.
    """
    parsed = parse_metric_chain(text)
    if not parsed:
        return None
    
    return validate_metric_chain(db, parsed, kpi_levels)


def format_chain_for_llm(
    metric_chain_json: Optional[Dict[str, Any]],
    kpi_configs: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Format metric chain for LLM prompt context.
    
    Args:
        metric_chain_json: Parsed/validated metric chain
        kpi_configs: Optional KPI metadata for enrichment
    
    Returns:
        Formatted string for LLM context, e.g.:
        "Metric Chain: signup → activation → revenue
        
        KPIs:
        - signup: User Registration (north_star)
        - activation: User Activation (strategic)
        - revenue: Monthly Revenue (strategic)"
    """
    if not metric_chain_json or not metric_chain_json.get("chain"):
        return "No metric chain defined."
    
    chain = metric_chain_json["chain"]
    raw = metric_chain_json.get("raw", " → ".join(chain))
    
    output = f"Metric Chain: {raw}\n"
    
    if kpi_configs:
        output += "\nKPIs:\n"
        # Build lookup
        kpi_lookup = {k["kpi_key"].lower(): k for k in kpi_configs if "kpi_key" in k}
        
        for key in chain:
            kpi_data = kpi_lookup.get(key.lower())
            if kpi_data:
                name = kpi_data.get("kpi_name", key)
                level = kpi_data.get("kpi_level", "")
                output += f"- {key}: {name} ({level})\n"
            else:
                output += f"- {key}: (not found in config)\n"
    
    return output.strip()


__all__ = [
    "parse_metric_chain",
    "validate_metric_chain",
    "parse_and_validate",
    "format_chain_for_llm",
]
