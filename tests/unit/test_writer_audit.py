"""Tests for V1.reports.writer_audit.

Confirms the report writes are byte-identical given identical input (L11
determinism) and that HALT runs leave no schedule.csv (Section 17 Fixture 2).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.reports import writer_audit
from V1.routes import audit


@pytest.fixture(scope="module")
def result(input_dir: Path, settings: Settings) -> audit.AuditResult:
    return audit.run(input_dir, settings)


def test_writes_audit_report_md(result: audit.AuditResult, tmp_path: Path) -> None:
    writer_audit.write(result, tmp_path)
    assert (tmp_path / "audit_report.md").exists()
    assert (tmp_path / "routing_cleaned.csv").exists()


def test_no_schedule_csv_on_halt_run(
    result: audit.AuditResult, tmp_path: Path
) -> None:
    """Section 17 Fixture 2 — schedule.csv must not exist after a HALT audit."""
    assert result.halt_findings  # precondition
    writer_audit.write(result, tmp_path)
    assert not (tmp_path / "schedule.csv").exists()


def test_audit_report_byte_identical_rerun(
    result: audit.AuditResult, tmp_path: Path
) -> None:
    """L11 / Section 12.2 — same input → byte-identical output."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    writer_audit.write(result, a)
    writer_audit.write(result, b)
    assert (a / "audit_report.md").read_bytes() == (b / "audit_report.md").read_bytes()
    assert (a / "routing_cleaned.csv").read_bytes() == (b / "routing_cleaned.csv").read_bytes()


def test_routing_cleaned_csv_preserves_leading_zeros(
    result: audit.AuditResult, tmp_path: Path
) -> None:
    """L23 — machine_id stays a string. Verifying via the joined column."""
    writer_audit.write(result, tmp_path)
    body = (tmp_path / "routing_cleaned.csv").read_text()
    # 0201 is a known mixer ID and must appear with its leading zero.
    assert "0201" in body
    assert ",201," not in body  # would indicate int coercion
