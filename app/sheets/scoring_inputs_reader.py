# productroadmap_sheet_project/app/sheets/scoring_inputs_reader.py

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.sheets.client import SheetsClient

# what does compile do here? creates regex object for reuse
_namespace_re = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[:\.-]\s*(.+?)\s*$") # e.g., "RICE: Reach" -> ("RICE", "Reach")


@dataclass
class ScoringInputsRow:
    initiative_key: str
    # framework -> param -> value
    framework_inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # selected overrides / admin flags
    active_scoring_framework: Optional[str] = None
    use_math_model: Optional[bool] = None
    # optional generic mappings
    extras: Dict[str, Any] = field(default_factory=dict)


class ScoringInputsReader:
    """Reads a namespaced, wide Scoring_Inputs sheet.

    Header convention:
      - "RICE: Reach", "RICE: Impact", "WSJF: Job Size", ...
      - Generic columns: "Initiative Key", "Active Scoring Framework", "Use Math Model",
        "Strategic Priority Coefficient", "Risk Level", "Time Sensitivity"
    """

    def __init__(self, client: SheetsClient, spreadsheet_id: str, tab_name: str = "Scoring_Inputs") -> None:
        self.client = client
        self.spreadsheet_id = spreadsheet_id
        self.tab_name = tab_name

    def _parse_header(self, headers: List[str]) -> List[Tuple[str, Optional[str], Optional[Tuple[str, str]]]]:
        """Return list of (raw_header, generic_key, namespaced) per column.
        - generic_key when header is well-known generic (e.g., initiative_key)
        - namespaced as (framework, param) when header is namespaced
        
        Supports two formats:
        1. Namespaced: "RICE: Reach" -> ("RICE", "rice_reach")
        2. Direct: "rice_reach" -> ("RICE", "rice_reach")
        """
        out: List[Tuple[str, Optional[str], Optional[Tuple[str, str]]]] = []
        for h in headers:
            raw = (h or "").strip() # avoid None
            lower = raw.lower()
            generic: Optional[str] = None
            namespaced: Optional[Tuple[str, str]] = None

            if lower in {"initiative key", "initiative_key"}:
                generic = "initiative_key"
            elif lower in {"active scoring framework", "active_framework", "framework"}:
                generic = "active_scoring_framework"
            elif lower in {"use math model", "use_math_model"}:
                generic = "use_math_model"
            elif lower in {"strategic priority coefficient", "strategic_priority_coefficient"}:
                generic = "strategic_priority_coefficient"
            elif lower in {"risk level", "risk_level"}:
                generic = "risk_level"
            elif lower in {"time sensitivity", "time_sensitivity"}:
                generic = "time_sensitivity"
            else:
                # Try namespaced format first: "RICE: Reach"
                m = _namespace_re.match(raw)
                if m:
                    fw = m.group(1).strip().upper()
                    param_raw = m.group(2).strip().lower().replace(" ", "_") # normalize
                    # prefix param with framework name (e.g., reach -> rice_reach)
                    param = f"{fw.lower()}_{param_raw}"
                    namespaced = (fw, param)
                else:
                    # Try direct format: "rice_reach", "wsjf_job_size"
                    # Check if it starts with a known framework prefix
                    if lower.startswith("rice_"):
                        namespaced = ("RICE", lower)
                    elif lower.startswith("wsjf_"):
                        namespaced = ("WSJF", lower)
                    elif lower.startswith("kano_"):
                        namespaced = ("KANO", lower)
                    elif lower.startswith("math_model_"):
                        # Extract framework name from pattern like "math_model_1_x"
                        parts = lower.split("_", 3)  # ["math", "model", "1", "x"]
                        if len(parts) >= 3:
                            fw_name = f"{parts[0]}_{parts[1]}_{parts[2]}".upper()  # "MATH_MODEL_1"
                            namespaced = (fw_name, lower)

            out.append((raw, generic, namespaced))
        return out

    @staticmethod
    def _to_bool(val: Any) -> Optional[bool]:
        if val is None:
            return None
        s = str(val).strip().lower()
        if s == "" or s == "none":
            return None
        if s in {"true", "1", "yes", "y"}:
            return True
        if s in {"false", "0", "no", "n"}:
            return False
        return None

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        s = str(val).strip()
        if s == "":
            return None
        try:
            return float(s)
        except Exception:
            return None

    def read(self) -> List[ScoringInputsRow]:
        """Read and parse the scoring inputs sheet."""
        # Read entire tab values; A1 notation without range returns full used range
        values = self.client.get_values(self.spreadsheet_id, f"{self.tab_name}")
        if not values:
            return []
        headers = [str(h) for h in (values[0] if values else [])]
        cols = self._parse_header(headers)

        rows: List[ScoringInputsRow] = []
        for raw_row in values[1:]:
            # skip all-empty lines
            if not any(c is not None and str(c).strip() != "" for c in raw_row):
                continue
            data = {}
            for idx, cell in enumerate(raw_row):
                if idx >= len(cols):
                    break
                raw, generic, namespaced = cols[idx]
                data[(generic, namespaced)] = cell

            # require initiative_key
            key_val = data.get(("initiative_key", None))
            key = str(key_val).strip() if key_val is not None else ""
            if not key:
                continue

            item = ScoringInputsRow(initiative_key=key)

            # generics
            act = data.get(("active_scoring_framework", None))
            if act is not None:
                s = str(act).strip()
                item.active_scoring_framework = s if s else None
            use_mm = data.get(("use_math_model", None))
            if use_mm is not None:
                item.use_math_model = self._to_bool(use_mm)
            # strong sync: always set extras, even if None (empty cell -> None)
            spc = data.get(("strategic_priority_coefficient", None))
            item.extras["strategic_priority_coefficient"] = self._to_float(spc)
            rl = data.get(("risk_level", None))
            if rl is None or str(rl).strip() == "":
                item.extras["risk_level"] = None
            else:
                item.extras["risk_level"] = str(rl).strip()
            ts = data.get(("time_sensitivity", None))
            if ts is None or str(ts).strip() == "":
                item.extras["time_sensitivity"] = None
            else:
                item.extras["time_sensitivity"] = str(ts).strip()

            # namespaced framework inputs
            for (generic, namespaced), cell in data.items():
                if namespaced is None:
                    continue
                fw, param = namespaced
                fw_dict = item.framework_inputs.setdefault(fw, {})
                # keep raw; numeric-like to float, else string
                num = self._to_float(cell)
                fw_dict[param] = num if num is not None else (str(cell).strip() if str(cell).strip() != "" else None)

            rows.append(item)
        return rows
