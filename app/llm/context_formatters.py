# productroadmap_sheet_project/app/llm/context_formatters.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.sheets.models import MetricsConfigRow


@dataclass(frozen=True)
class LLMContextFormatResult:
    text: str
    included_sections: int
    included_lines: int
    total_chars: int
    truncated: bool


def format_llm_context_sections(
    sections: Mapping[str, Sequence[str]],
    *,
    max_total_chars: int = 12000,
) -> LLMContextFormatResult:
    """Convert LLM context sections into labeled prompt text blocks."""
    if not sections:
        return LLMContextFormatResult(
            text="",
            included_sections=0,
            included_lines=0,
            total_chars=0,
            truncated=False,
        )

    blocks: list[str] = []
    included_sections = 0
    included_lines = 0
    truncated = False

    for header, lines in sections.items():
        block_lines = [f"[{header}]"]
        line_count = 0

        for line in lines:
            candidate_block_lines = [*block_lines, f"- {line}"]
            candidate_block = "\n".join(candidate_block_lines)
            candidate_text = "\n\n".join([*blocks, candidate_block])
            if len(candidate_text) > max_total_chars:
                truncated = True
                break

            block_lines = candidate_block_lines
            line_count += 1

        if line_count == 0:
            if truncated:
                break
            continue

        blocks.append("\n".join(block_lines))
        included_sections += 1
        included_lines += line_count

        if truncated:
            break

    text = "\n\n".join(blocks)
    return LLMContextFormatResult(
        text=text,
        included_sections=included_sections,
        included_lines=included_lines,
        total_chars=len(text),
        truncated=truncated,
    )

def format_metrics_config_rows(
    rows: Sequence[MetricsConfigRow],
    *,
    max_total_chars: int = 6000,
) -> LLMContextFormatResult:
    """Convert Metrics_Config rows into prompt-ready KPI definition bullets."""
    if not rows:
        return LLMContextFormatResult(
            text="",
            included_sections=0,
            included_lines=0,
            total_chars=0,
            truncated=False,
        )

    lines: list[str] = []
    truncated = False
    included = 0

    def _row_to_line(row: MetricsConfigRow) -> str:
        parts = [f"{row.kpi_key}"]
        if row.kpi_name:
            parts.append(f"name={row.kpi_name}")
        if row.kpi_level:
            parts.append(f"level={row.kpi_level}")
        if row.unit:
            parts.append(f"unit={row.unit}")
        if row.description:
            parts.append(f"description={row.description}")
        return "- " + " | ".join(parts)

    for row in rows:
        line = _row_to_line(row)
        candidate_lines = [*lines, line]
        candidate_text = "\n".join(candidate_lines)
        if len(candidate_text) > max_total_chars:
            truncated = True
            break
        lines = candidate_lines
        included += 1

    text = "\n".join(lines)
    return LLMContextFormatResult(
        text=text,
        included_sections=1 if text else 0,
        included_lines=included,
        total_chars=len(text),
        truncated=truncated,
    )


__all__ = [
    "LLMContextFormatResult",
    "format_llm_context_sections",
    "format_metrics_config_rows",
]