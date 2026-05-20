"""Tests for V1.utilities.machine_parser.

Covers every shape observed in the live routing sheet plus determinism +
leading-zero preservation invariants (L23).
"""
from __future__ import annotations

import math

import pytest

from V1.utilities.machine_parser import join_machines, parse_machines


class TestParseMachines:
    def test_double_double_quote_no_leading(self) -> None:
        raw = "0201'',''0202'',''0204'',''0205'',''0206''"
        assert parse_machines(raw) == ["0201", "0202", "0204", "0205", "0206"]

    def test_double_double_quote_with_leading(self) -> None:
        raw = "'0201'',''0202'',''0204'',''0205'',''0206''"
        assert parse_machines(raw) == ["0201", "0202", "0204", "0205", "0206"]

    def test_single_quoted_single_value(self) -> None:
        assert parse_machines("'FRC'") == ["FRC"]

    def test_bare_single_value(self) -> None:
        assert parse_machines("FRC") == ["FRC"]

    def test_comma_separated_two_tokens(self) -> None:
        assert parse_machines("WBC, WBCNew") == ["WBC", "WBCNew"]

    def test_value_with_space(self) -> None:
        # CapStrip Slitter is one machine name, not two
        assert parse_machines("'CapStrip Slitter'") == ["CapStrip Slitter"]

    def test_building_pool(self) -> None:
        raw = "'7001'',''7002'',''7003'',''7004'',''6001'',''6002'',''6003'',''6004''"
        got = parse_machines(raw)
        assert got == ["6001", "6002", "6003", "6004", "7001", "7002", "7003", "7004"]

    def test_nan_returns_empty(self) -> None:
        assert parse_machines(math.nan) == []

    def test_none_returns_empty(self) -> None:
        assert parse_machines(None) == []

    def test_empty_string_returns_empty(self) -> None:
        assert parse_machines("") == []
        assert parse_machines("   ") == []

    def test_leading_zeros_preserved_l23(self) -> None:
        """L23 — machine_id is string everywhere; never coerce to int."""
        got = parse_machines("'0201'',''0202''")
        for m in got:
            assert isinstance(m, str)
            assert m.startswith("0")

    def test_deterministic_sort(self) -> None:
        """Determinism: same input string always returns same list."""
        raw = "'7004'',''6001'',''7002''"
        runs = {tuple(parse_machines(raw)) for _ in range(50)}
        assert len(runs) == 1
        assert list(runs)[0] == ("6001", "7002", "7004")

    def test_dedup(self) -> None:
        assert parse_machines("FRC, FRC") == ["FRC"]


class TestJoinMachines:
    def test_pipe_joined_sorted(self) -> None:
        assert join_machines(["7004", "6001", "7002"]) == "6001|7002|7004"

    def test_empty(self) -> None:
        assert join_machines([]) == ""

    def test_dedup(self) -> None:
        assert join_machines(["a", "a", "b"]) == "a|b"
