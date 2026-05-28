"""Audit module tests against the real pilot inputs.

These are integration-style — they exercise audit.run() on input/ as-is. The
inputs are stable and small enough that this is the fastest path to high
confidence.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.enums import FindingSeverity
from V1.config.halt_codes import HaltCode
from V1.config.settings import Settings
from V1.routes import audit


@pytest.fixture(scope="module")
def result(nulled_input_dir: Path, settings: Settings) -> audit.AuditResult:
    """Pilot inputs with BD Fillering proc_time nulled so the HALT case
    fires regardless of the live input's current state."""
    return audit.run(nulled_input_dir, settings)


class TestPilotScope:
    def test_42_pilot_curing_rows(self, result: audit.AuditResult, settings: Settings) -> None:
        assert (result.curing_df["SKUCode"] == settings.sku_code).all()
        assert len(result.curing_df) == 42

    def test_curing_starttime_parsed(self, result: audit.AuditResult) -> None:
        first = result.curing_df.iloc[0]["StartTime"]
        # M/D/YYYY HH:MM format, sorted by StartTime
        assert first.year == 2026
        assert first.month == 5

    def test_curing_machine_is_string_l23(self, result: audit.AuditResult,
                                          settings: Settings) -> None:
        assert (result.curing_df["Machine"] == settings.curing_press).all()
        for m in result.curing_df["Machine"]:
            assert isinstance(m, str)


class TestRoutingCleaning:
    def test_routing_raw_count(self, result: audit.AuditResult) -> None:
        assert len(result.routing_df) == 62

    def test_cleaned_drops_capstrip(self, result: audit.AuditResult,
                                    settings: Settings) -> None:
        for col in ("routed_product", "finished_product_stock"):
            for v in result.routing_cleaned_df[col]:
                assert v not in settings.capstrip_items, (
                    f"Capstrip item leaked into routing_cleaned: {v}"
                )

    def test_cleaned_dedups_routed_product_op_seq(
        self, result: audit.AuditResult
    ) -> None:
        key = result.routing_cleaned_df[["routed_product", "operation_seq"]]
        assert not key.duplicated().any()

    def test_machines_list_is_list_of_strings(self, result: audit.AuditResult) -> None:
        for ml in result.routing_cleaned_df["machines_list"]:
            assert isinstance(ml, list)
            for m in ml:
                assert isinstance(m, str)

    def test_eligible_machine_count_matches_list_length(
        self, result: audit.AuditResult
    ) -> None:
        df = result.routing_cleaned_df
        for _, row in df.iterrows():
            assert row["eligible_machine_count"] == len(row["machines_list"])

    def test_cleaned_count_known(self, result: audit.AuditResult) -> None:
        # L12 reversed 2026-05-28 — Capstrip now in scope, so the 5 Capstrip
        # rows are NO LONGER dropped:
        # 62 raw - 1 EHT1000 dup - 8 silently-collapsed shared master
        # compounds = 53.
        assert len(result.routing_cleaned_df) == 53


class TestFindings:
    """Fixture-driven tests for Section 17 cases that map onto the audit."""

    def test_fixture_2_bd_fillering_halt(self, result: audit.AuditResult) -> None:
        """Section 17 Fixture 2 — null proc_time on BD-12843443-4 Fillering → HALT."""
        halts = [f for f in result.halt_findings
                 if f.code == "AUDIT_NULL_PROC_TIME"
                 and f.item_code == "BD-12843443-4"]
        assert len(halts) == 1, "Expected exactly one HALT for BD Fillering"
        h = halts[0]
        assert h.severity == FindingSeverity.HALT
        assert "FILLERING" in h.message.upper()
        assert h.excel_row() == 61

    def test_fixture_3_eht1000_duplicate_row(self, result: audit.AuditResult) -> None:
        """Section 17 Fixture 3 — EHT1000 calendering duplicate, NaN row dropped."""
        dups = [f for f in result.warn_findings
                if f.code == "ROUTING_DUPLICATE_DROPPED"
                and f.item_code == "EHT1000"]
        assert len(dups) == 1
        f = dups[0]
        assert f.excel_row() == 51  # pandas row 49

        # And it must NOT appear in routing_cleaned_df.
        key = result.routing_cleaned_df[["routed_product", "operation_seq"]]
        eht_cal = key[(key["routed_product"] == "EHT1000")
                      & (key["operation_seq"] == 40)]
        assert len(eht_cal) == 1  # exactly one canonical row remains

    def test_fixture_4_b460_no_longer_mixed_unit(
        self, result: audit.AuditResult
    ) -> None:
        """Section 17 Fixture 4 — the latest aging dataset CORRECTED B460's
        mixed-unit quirk: it is now 4 Hours / 96 Hours (both Hours), which
        still normalises to (240, 5760) min — verified by
        test_unit_conversion.py::TestNormalise::test_fixture_4_b460_in_aging_df.

        Because the live aging data is now clean, the audit should raise NO
        AGING_MIXED_UNITS finding. The detector logic itself is still
        covered by test_mixed_unit_detector_synthetic below.
        """
        mixed = [f for f in result.warn_findings if f.code == "AGING_MIXED_UNITS"]
        assert len(mixed) == 0, (
            "Latest aging data has no mixed-unit rows — detector should stay silent"
        )

    def test_mixed_unit_detector_synthetic(self) -> None:
        """Detector still fires on a genuinely mixed-unit row (regression
        guard, decoupled from the live dataset)."""
        import pandas as pd
        from V1.routes.audit import _check_mixed_unit_aging
        from V1.config.enums import FindingSeverity

        synthetic = pd.DataFrame({
            "ItemCode": ["FAKE_MIX"],
            "MinAging": [4], "MinAgingUnit": ["Hours"],
            "MaxAging": [4], "MaxAgingUnit": ["Days"],
        })
        findings: list[audit.AuditFinding] = []
        _check_mixed_unit_aging(synthetic, findings)
        assert len(findings) == 1
        assert findings[0].code == "AGING_MIXED_UNITS"
        assert findings[0].severity == FindingSeverity.WARN
        assert "FAKE_MIX" in findings[0].extras["item_codes"]

    def test_capstrip_not_dropped_after_l12_reversal(
        self, result: audit.AuditResult, settings: Settings
    ) -> None:
        # L12 reversed 2026-05-28 — Capstrip is in scope, so the audit must
        # NOT drop any Capstrip routing rows, and the exclusion list is empty.
        cap = [f for f in result.warn_findings
               if f.code == "CAPSTRIP_ROUTING_DROPPED"]
        assert cap == [], "Capstrip should no longer be dropped (L12 reversed)"
        assert settings.capstrip_items == frozenset()

    def test_pilot_items_have_aging(self, result: audit.AuditResult,
                                    settings: Settings) -> None:
        aging_ids = set(result.aging_df["ItemCode"].astype(str))
        for item in settings.green_tyre_components:
            assert item in aging_ids
        assert settings.green_tyre_code in aging_ids

    def test_pilot_items_have_itemtype(self, result: audit.AuditResult,
                                       settings: Settings) -> None:
        itype_ids = set(result.itemtype_df["ItemCode"].astype(str))
        for item in settings.green_tyre_components:
            assert item in itype_ids
        assert settings.green_tyre_code in itype_ids


class TestHaltCodeMapping:
    def test_null_proc_time_maps_to_code_10(self) -> None:
        assert audit.HALT_CODE_MAP["AUDIT_NULL_PROC_TIME"] == HaltCode.AUDIT_NULL_PROC_TIME
        assert int(HaltCode.AUDIT_NULL_PROC_TIME) == 10


class TestDeduplication:
    def test_aging_dedup_one_row_per_itemcode(
        self, result: audit.AuditResult
    ) -> None:
        assert result.aging_df["ItemCode"].is_unique

    def test_itemtype_dedup_one_row_per_itemcode(
        self, result: audit.AuditResult
    ) -> None:
        assert result.itemtype_df["ItemCode"].is_unique
