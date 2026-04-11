# productroadmap_sheet_project/app/sheets/llm_context_reader.py
from __future__ import annotations

import logging
from typing import Dict, List

from app.sheets.client import SheetsClient

logger = logging.getLogger(__name__)


class LLMContextReader:
    """Read a flexible column-based LLM context sheet.

    Expected shape:
    - Row 1: section headers
    - Rows 2+: free-text lines under each section

    Parsing rules:
    - Ignore blank headers
    - Ignore blank cells under headers
    - Preserve row order within a section
    - Trim whitespace
    - Skip fully empty sections
    """

    def __init__(
        self,
        client: SheetsClient,
        spreadsheet_id: str,
        tab_name: str,
        *,
        max_sections: int = 20,
        max_scan_rows: int = 300,
        max_lines_per_section: int = 50,
        max_chars_per_line: int = 1000,
    ) -> None:
        self.client = client
        self.spreadsheet_id = spreadsheet_id
        self.tab_name = tab_name
        self.max_sections = max_sections
        self.max_scan_rows = max_scan_rows
        self.max_lines_per_section = max_lines_per_section
        self.max_chars_per_line = max_chars_per_line

    def read(self) -> Dict[str, List[str]]:
        grid_rows, grid_cols = self.client.get_sheet_grid_size(self.spreadsheet_id, self.tab_name)
        if grid_rows <= 0 or grid_cols <= 0:
            logger.info("llm_context_reader.empty_grid", extra={"tab": self.tab_name})
            return {}

        end_col = _col_index_to_a1(min(grid_cols, self.max_sections))
        end_row = min(grid_rows, self.max_scan_rows)
        values = self.client.get_values(
            self.spreadsheet_id,
            f"{self.tab_name}!A1:{end_col}{end_row}",
        )
        if not values:
            logger.info("llm_context_reader.empty_sheet", extra={"tab": self.tab_name})
            return {}

        header_row = values[0] if values else []
        data_rows = values[1:] if len(values) > 1 else []

        sections: Dict[str, List[str]] = {}
        truncated_sections = 0
        truncated_lines = 0

        for col_idx, raw_header in enumerate(header_row[: self.max_sections]):
            header = str(raw_header or "").strip()
            if not header:
                continue

            lines: List[str] = []
            for row in data_rows:
                if col_idx >= len(row):
                    continue
                text = str(row[col_idx] or "").strip()
                if not text:
                    continue

                if len(text) > self.max_chars_per_line:
                    text = text[: self.max_chars_per_line].rstrip()
                    truncated_lines += 1

                lines.append(text)
                if len(lines) >= self.max_lines_per_section:
                    truncated_sections += 1
                    break

            if lines:
                sections[header] = lines

        logger.info(
            "llm_context_reader.read_done",
            extra={
                "tab": self.tab_name,
                "section_count": len(sections),
                "entry_count": sum(len(lines) for lines in sections.values()),
                "scanned_rows": end_row,
                "truncated_sections": truncated_sections,
                "truncated_lines": truncated_lines,
            },
        )
        return sections


def _col_index_to_a1(idx: int) -> str:
    if idx <= 0:
        return "A"
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


__all__ = ["LLMContextReader"]