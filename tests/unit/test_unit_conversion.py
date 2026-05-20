"""Tests for V1.utilities.unit_conversion (L20)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from V1.config.settings import Settings
from V1.routes import audit
from V1.utilities.unit_conversion import (
    NormalisedResult,
    aging_to_minutes,
    normalise,
    proc_time_to_minutes,
)


class TestAgingToMinutes:
    def test_days(self) -> None:
        assert aging_to_minutes(4, "Days") == 4 * 1440

    def test_hours(self) -> None:
        assert aging_to_minutes(4, "Hours") == 240

    def test_minutes(self) -> None:
        assert aging_to_minutes(30, "Minutes") == 30

    def test_min_alias(self) -> None:
        """Live Aging Master uses 'Min' alongside 'Minutes' — accepted."""
        assert aging_to_minutes(30, "Min") == 30

    def test_case_insensitive(self) -> None:
        assert aging_to_minutes(4, "days") == 5760
        assert aging_to_minutes(4, "HOURS") == 240

    def test_ceil_on_fraction(self) -> None:
        # 0.5 Days = 720 min, exact
        assert aging_to_minutes(0.5, "Days") == 720
        # 0.5 Hours = 30 min, exact
        assert aging_to_minutes(0.5, "Hours") == 30
        # 1.5 Minutes → ceil = 2
        assert aging_to_minutes(1.5, "Minutes") == 2

    def test_nan_returns_none(self) -> None:
        assert aging_to_minutes(float("nan"), "Days") is None
        assert aging_to_minutes(4, None) is None

    def test_unknown_unit_returns_none(self) -> None:
        assert aging_to_minutes(4, "KGS") is None
        assert aging_to_minutes(4, "Weeks") is None

    def test_zero_value(self) -> None:
        assert aging_to_minutes(0, "Days") == 0
        assert aging_to_minutes(0, "Hours") == 0

    def test_fixture_4_b460(self) -> None:
        """Section 17 Fixture 4 — B460: 4 Hours min, 4 Days max → (240, 5760)."""
        assert aging_to_minutes(4, "Hours") == 240
        assert aging_to_minutes(4, "Days") == 5760


class TestProcTimeToMinutes:
    def test_sec_per_batch(self) -> None:
        # 750 SEC = 12.5 min → ceil = 13
        assert proc_time_to_minutes(750, "SEC/BATCH") == 13

    def test_sec(self) -> None:
        assert proc_time_to_minutes(120, "SEC") == 2

    def test_min(self) -> None:
        assert proc_time_to_minutes(15, "MIN") == 15
        assert proc_time_to_minutes(15.5, "MIN") == 16

    def test_m_per_min_deferred(self) -> None:
        """M/MIN needs lot qty — deferred to time_calculation."""
        assert proc_time_to_minutes(20, "M/MIN") is None

    def test_nan(self) -> None:
        assert proc_time_to_minutes(float("nan"), "SEC/BATCH") is None
        assert proc_time_to_minutes(None, "SEC/BATCH") is None
        assert proc_time_to_minutes(750, None) is None

    def test_unknown_uom(self) -> None:
        assert proc_time_to_minutes(750, "FURLONGS") is None

    def test_real_pilot_171_sec_batch(self) -> None:
        """Live MB349 op_seq 10 has proc_time=171 SEC/BATCH → 171/60=2.85 → 3."""
        assert proc_time_to_minutes(171, "SEC/BATCH") == 3


class TestNormalise:
    """End-to-end on the real AuditResult."""

    @pytest.fixture(scope="class")
    def audit_result(self, input_dir: Path, settings: Settings) -> audit.AuditResult:
        return audit.run(input_dir, settings)

    @pytest.fixture(scope="class")
    def norm(self, audit_result: audit.AuditResult,
             settings: Settings) -> NormalisedResult:
        return normalise(audit_result, settings)

    def test_t0_is_settings_default(self, norm: NormalisedResult,
                                    settings: Settings) -> None:
        assert norm.t0 == settings.t0_default

    def test_aging_has_minute_columns(self, norm: NormalisedResult) -> None:
        assert "min_aging_min" in norm.aging_df.columns
        assert "max_aging_min" in norm.aging_df.columns

    def test_fixture_4_b460_in_aging_df(self, norm: NormalisedResult) -> None:
        """Section 17 Fixture 4 acceptance: cleaned aging shows (240, 5760)."""
        b460 = norm.aging_df[norm.aging_df["ItemCode"].astype(str) == "B460"]
        assert len(b460) == 1
        row = b460.iloc[0]
        assert row["min_aging_min"] == 240
        assert row["max_aging_min"] == 5760

    def test_pilot_components_have_minute_aging(self, norm: NormalisedResult,
                                                settings: Settings) -> None:
        for item in settings.green_tyre_components:
            row = norm.aging_df[norm.aging_df["ItemCode"].astype(str) == item]
            assert len(row) == 1, f"{item} should have exactly one aging row"
            mn, mx = row.iloc[0]["min_aging_min"], row.iloc[0]["max_aging_min"]
            assert mn is not None and pd.notna(mn), f"{item} min_aging_min missing"
            assert mx is not None and pd.notna(mx), f"{item} max_aging_min missing"
            assert int(mn) <= int(mx), f"{item} min > max"

    def test_routing_has_proc_time_min(self, norm: NormalisedResult) -> None:
        assert "proc_time_min" in norm.routing_df.columns

    def test_routing_sec_batch_rows_converted(self, norm: NormalisedResult) -> None:
        mask = norm.routing_df["proc_time_UOM"] == "SEC/BATCH"
        sub = norm.routing_df[mask]
        assert (sub["proc_time_min"].notna()).all()
        # Spot-check: 171 SEC/BATCH = 3
        mb349 = sub[(sub["routed_product"] == "MB349")
                    & (sub["operation_seq"] == 10)]
        assert len(mb349) == 1
        assert int(mb349.iloc[0]["proc_time_min"]) == 3

    def test_routing_m_per_min_rows_deferred(self, norm: NormalisedResult) -> None:
        """M/MIN rows have proc_time_min = None (per-lot in time_calculation)."""
        mask = norm.routing_df["proc_time_UOM"] == "M/MIN"
        sub = norm.routing_df[mask]
        assert len(sub) > 0  # there ARE M/MIN rows in the pilot routing
        assert sub["proc_time_min"].isna().all()

    def test_curing_has_start_end_min(self, norm: NormalisedResult,
                                      settings: Settings) -> None:
        assert "start_min" in norm.curing_df.columns
        assert "end_min" in norm.curing_df.columns
        # All non-negative since first curing is well after t0=2026-05-01 07:00.
        assert (norm.curing_df["start_min"] > 0).all()
        # end_min > start_min for every row
        assert (norm.curing_df["end_min"] > norm.curing_df["start_min"]).all()

    def test_first_curing_minute(self, norm: NormalisedResult) -> None:
        """First pilot curing block per CLAUDE.md is 2026-05-17 06:49."""
        first = norm.curing_df.iloc[0]
        # (2026-05-17 06:49 - 2026-05-01 07:00) = 16 days - 11 min = 23029 min
        expected = 16 * 1440 - 11
        assert int(first["start_min"]) == expected

    def test_audit_frames_not_mutated(self, audit_result: audit.AuditResult,
                                      norm: NormalisedResult) -> None:
        """normalise() is a pure function — original AuditResult untouched."""
        assert "min_aging_min" not in audit_result.aging_df.columns
        assert "proc_time_min" not in audit_result.routing_cleaned_df.columns
        assert "start_min" not in audit_result.curing_df.columns
