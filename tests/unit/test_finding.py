"""Tests for V1.models.finding."""
from __future__ import annotations

from V1.config.enums import FindingSeverity
from V1.models.finding import AuditFinding


def test_excel_row_is_pandas_row_plus_two() -> None:
    f = AuditFinding(
        severity=FindingSeverity.WARN, code="X",
        message="hi", sheet="Routing", source_row=49,
    )
    assert f.excel_row() == 51


def test_excel_row_none_when_no_source_row() -> None:
    f = AuditFinding(severity=FindingSeverity.HALT, code="X", message="hi")
    assert f.excel_row() is None


def test_md_line_contains_severity_and_code() -> None:
    f = AuditFinding(
        severity=FindingSeverity.HALT, code="AUDIT_NULL_PROC_TIME",
        message="null proc_time", sheet="Routing", source_row=59,
        item_code="BD-12843443-4",
    )
    line = f.to_md_line()
    assert "[HALT]" in line
    assert "`AUDIT_NULL_PROC_TIME`" in line
    assert "BD-12843443-4" in line
    assert "Excel row 61" in line


def test_finding_is_frozen() -> None:
    f = AuditFinding(severity=FindingSeverity.WARN, code="X", message="m")
    import dataclasses
    try:
        f.code = "Y"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("AuditFinding should be frozen")
