"""AuditFinding dataclass — HALT vs Warn split per Section 9."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from V1.config.enums import FindingSeverity


@dataclass(frozen=True)
class AuditFinding:
    """One data-quality finding emitted by the audit module.

    `source_row` is the 0-indexed pandas row in the original sheet (so the
    user can cross-reference with the input file). The corresponding Excel
    row is `source_row + 2` (header on row 1).
    """
    severity: FindingSeverity
    code: str                           # Stable short identifier (e.g. "EHT1000_DUP_ROW")
    message: str                        # Human-readable one-liner
    sheet: str | None = None            # Source sheet name when relevant
    source_row: int | None = None       # 0-indexed pandas row
    item_code: str | None = None        # Item code when the finding is item-scoped
    extras: dict[str, Any] = field(default_factory=dict)

    def excel_row(self) -> int | None:
        return None if self.source_row is None else self.source_row + 2

    def to_md_line(self) -> str:
        parts: list[str] = [f"[{self.severity.value}]", f"`{self.code}`"]
        if self.sheet is not None:
            loc = f"`{self.sheet}`"
            if self.source_row is not None:
                loc += f" pandas row {self.source_row} (Excel row {self.excel_row()})"
            parts.append(loc)
        if self.item_code is not None:
            parts.append(f"item=`{self.item_code}`")
        parts.append(self.message)
        return " — ".join(parts)
