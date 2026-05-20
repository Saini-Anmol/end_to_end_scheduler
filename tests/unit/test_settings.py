"""Tests for V1.config.settings — pilot.yaml is the SoT for tunables."""
from __future__ import annotations

from datetime import datetime

from V1.config.settings import Settings, load_settings


def test_pilot_yaml_loads() -> None:
    s = load_settings()
    assert isinstance(s, Settings)


def test_locked_pilot_values() -> None:
    """These values are pinned in CLAUDE.md and must never silently change."""
    s = load_settings()
    assert s.sku_code == "1325220516095HTMX0"
    assert s.green_tyre_code == "GT2056516TAXIMXTL"
    # L23: curing_press is string — leading zeros matter.
    assert isinstance(s.curing_press, str)
    assert s.curing_press == "14811"
    assert s.efficiency_factor == 0.95
    assert s.default_transfer_min == 10
    assert s.changeover_min_v1 == 0
    assert s.building_primary == "6001"
    assert s.t0_default == datetime(2026, 5, 1, 7, 0)
    assert s.t0_guardrail_enabled is True


def test_building_pool_is_strings_l23() -> None:
    s = load_settings()
    for m in s.building_pool:
        assert isinstance(m, str)
    assert s.building_primary in s.building_pool
    # Primary is the lowest in the pool (L18 placeholder).
    assert s.building_primary == min(s.building_pool)


def test_8_in_scope_components() -> None:
    s = load_settings()
    assert len(s.green_tyre_components) == 8
    assert "BD-12843443-4" in s.green_tyre_components


def test_capstrip_exclusion_list_l12() -> None:
    s = load_settings()
    for name in ["CAP 66 - CAPSTRIP", "CAP 66-MOTHERROLL", "CAP 66", "B616M", "MB614"]:
        assert name in s.capstrip_items


def test_run_id_format_hhmm_dd_mm_yyyy() -> None:
    s = load_settings()
    assert s.run_id_format == "%H%M-%d-%m-%Y"
    assert datetime(2026, 5, 1, 7, 0).strftime(s.run_id_format) == "0700-01-05-2026"


def test_settings_is_frozen() -> None:
    s = load_settings()
    import dataclasses
    assert dataclasses.is_dataclass(s)
    try:
        s.sku_code = "X"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Settings should be frozen")
