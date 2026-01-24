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
    
    Args:
        db: Database session
        metric_chain_json: Parsed metric chain dict with "chain" field
        kpi_levels: Optional filter for KPI levels (e.g., ["north_star", "strategic"])
    
    Returns:
        {
            "chain": ["signup", "activation", "revenue"],
            "validated": True,
            "invalid_keys": [],
            "valid_keys": ["signup", "activation", "revenue"],
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
        }
    
    chain = metric_chain_json["chain"]
    
    # Load allowed KPI keys
    configs = db.query(OrganizationMetricConfig).all()
    allowed_keys: Set[str] = set()
    
    for cfg in configs:
        meta = cfg.metadata_json or {}
        is_active = meta.get("is_active", True)
        
        if not is_active:
            continue
        
        if kpi_levels and cfg.kpi_level not in kpi_levels:
            continue
        
        if cfg.kpi_key is not None:
            allowed_keys.add(cfg.kpi_key.lower())
    
    # Validate each key in chain
    valid_keys = [k for k in chain if k.lower() in allowed_keys]
    invalid_keys = [k for k in chain if k.lower() not in allowed_keys]
    
    return {
        "chain": chain,
        "validated": len(invalid_keys) == 0,
        "invalid_keys": invalid_keys,
        "valid_keys": valid_keys,
        "all_allowed_keys": sorted(list(allowed_keys)),
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
