"""Tests for V1.setups.bootstrap — end-to-end Module-1 wiring."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from V1.config.halt_codes import HaltCode
from V1.config.settings import Settings
from V1.setups import bootstrap


def test_bootstrap_halts_on_bd_fillering(
    nulled_input_dir: Path, settings: Settings, tmp_output_root: Path
) -> None:
    code = bootstrap.run(settings, input_dir=nulled_input_dir,
                          output_root=tmp_output_root)
    assert code == int(HaltCode.AUDIT_NULL_PROC_TIME) == 10
    # Audit artefacts exist; downstream files do not.
    runs = list(tmp_output_root.iterdir())
    assert len(runs) == 1
    out = runs[0]
    assert (out / "audit_report.md").exists()
    # The HALT path bundles the routing-cleaned table into btp_schedule.xlsx;
    # no standalone CSV is emitted by the pipeline.
    assert (out / "btp_schedule.xlsx").exists()
    assert not (out / "routing_cleaned.csv").exists()
    assert not (out / "schedule.csv").exists()


def test_bootstrap_audit_report_names_binding_finding(
    nulled_input_dir: Path, settings: Settings, tmp_output_root: Path
) -> None:
    """Fixture 2 acceptance — audit_report.md must NAME the offending row."""
    bootstrap.run(settings, input_dir=nulled_input_dir,
                   output_root=tmp_output_root)
    out = next(tmp_output_root.iterdir())
    text = (out / "audit_report.md").read_text()
    assert "HALT" in text
    assert "BD-12843443-4" in text
    assert "AUDIT_NULL_PROC_TIME" in text
    # Section 8.D — no silent imputation language
    assert "Section 8.D" in text or "Planner must supply" in text
