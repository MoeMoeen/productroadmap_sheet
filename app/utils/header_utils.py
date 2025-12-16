from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def normalize_header(name: str) -> str:
    """Normalize sheet header to lowercase field name format.

    Supports both formats:
    - Direct: "rice_value_score" → "rice_value_score"
    - Namespaced: "RICE: Value Score" → "rice_value_score"
    Also normalizes hyphens and collapses duplicate underscores.
    """
    n = (name or "").strip().lower()
    if ":" in n:
        fw, param = [p.strip() for p in n.split(":", 1)]
        n = f"{fw}_{param.replace(' ', '_')}"
    else:
        n = n.replace(" ", "_")
    n = n.replace("-", "_")
    while "__" in n:
        n = n.replace("__", "_")
    return n.strip("_")


def resolve_indices(headers: List[str], header_map: Dict[str, List[str]]) -> Dict[str, int]:
    """Resolve column indices for a tab, using alias maps.

    Args:
        headers: Raw header row from sheet (strings)
        header_map: Canonical field -> list of accepted aliases

    Returns:
        Mapping of canonical field -> column index (0-based)
    """
    norm_headers = [normalize_header(h) for h in headers]

    # Build normalized alias lookup
    alias_lookup: Dict[str, str] = {}
    for field, aliases in header_map.items():
        for a in aliases:
            alias_lookup[normalize_header(a)] = field

    col_map: Dict[str, int] = {}
    for i, nh in enumerate(norm_headers):
        if nh in alias_lookup:
            col_map[alias_lookup[nh]] = i
    return col_map


def get_value_by_header_alias(
    row: Dict[str, Any], primary_name: str, aliases: Iterable[str] | None = None
) -> Optional[Any]:
    """Return the value from row matching primary header name or any alias.

    Matching is case-insensitive and normalized via normalize_header.
    """
    targets = {normalize_header(primary_name)}
    for a in (aliases or []):
        targets.add(normalize_header(a))
    for k, v in row.items():
        if normalize_header(str(k)) in targets:
            return v
    return None


__all__ = ["normalize_header", "resolve_indices", "get_value_by_header_alias"]
