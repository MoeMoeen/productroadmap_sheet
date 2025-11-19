from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def normalize_header(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.replace("-", "_").replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


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
