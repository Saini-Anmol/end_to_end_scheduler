"""Messy machine-cell normaliser + per-lot eligibility lookup
(Section 8.F, finding #6 / #2).

Handles the routing's `machines` column whose values come in several shapes:

    "0201'',''0202'',''0204'',''0205'',''0206''"     # double-double-quote separator
    "'0201'',''0202'',''0204'',''0205'',''0206''"    # with leading quote
    "FRC"                                            # single value
    "WBC, WBCNew"                                    # comma-separated, two tokens
    "'CapStrip Slitter'"                             # single value with embedded space

machine_id is always returned as a string — leading zeros in the 0201-0206
mixer pool must be preserved (L23).
"""
from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


# Any sequence of quote chars (possibly empty) flanking a comma collapses
# to a single comma. The outer .strip() then drops residual edge quotes.
_QUOTE_COMMA_RE = re.compile(r"['\"]*\s*,\s*['\"]*")
_EDGE_TRIM_CHARS = " '\"\t"


def parse_machines(raw: object) -> list[str]:
    """Parse a machines cell into a sorted, de-duplicated list of strings.

    Sorting is alphabetical for determinism. The audit step uses the *length*
    of the returned list as `eligible_machine_count` (Section 8.F).

    Returns an empty list for NaN / empty / whitespace-only inputs.
    """
    if raw is None:
        return []
    if isinstance(raw, float) and pd.isna(raw):
        return []
    s = str(raw).strip()
    if not s:
        return []
    normalised = _QUOTE_COMMA_RE.sub(",", s)
    normalised = normalised.strip(_EDGE_TRIM_CHARS)
    pieces = [p.strip(_EDGE_TRIM_CHARS) for p in normalised.split(",")]
    cleaned = [p for p in pieces if p]
    return sorted(set(cleaned))


def join_machines(machines: Iterable[str]) -> str:
    """Pipe-join a machines list for CSV output. Sorted, dedup-safe."""
    return "|".join(sorted(set(machines)))


# --- per-(item, op_seq) lookup --------------------------------------------

def eligible_machines(routing_df: pd.DataFrame, item: str, op_seq: int) -> list[str]:
    """Return the eligible machine list for a specific (item, op_seq) routing row.

    Always returns a list of strings (L23 — machine_id is string everywhere).
    Order is the canonical sort produced by `parse_machines`. Raises KeyError
    if the routing has no matching row.
    """
    rows = routing_df[
        (routing_df["routed_product"] == item)
        & (routing_df["operation_seq"] == op_seq)
    ]
    if len(rows) == 0:
        raise KeyError(f"No routing row for (item={item!r}, op_seq={op_seq})")
    if len(rows) > 1:
        raise ValueError(
            f"Routing has multiple rows for (item={item!r}, op_seq={op_seq}) "
            f"after dedup — check audit."
        )
    row = rows.iloc[0]
    # Prefer the pre-parsed list (added by audit). Fall back to live parse.
    ml = row.get("machines_list")
    if isinstance(ml, list):
        return [str(m) for m in ml]
    return parse_machines(row.get("machines"))


def build_eligibility_index(
    routing_df: pd.DataFrame,
) -> dict[tuple[str, int], list[str]]:
    """One-shot eligibility index keyed by (item, op_seq).

    Forward scheduler builds this once and reuses across dispatch decisions.
    """
    out: dict[tuple[str, int], list[str]] = {}
    for _, row in routing_df.iterrows():
        item = str(row["routed_product"])
        op_seq = int(row["operation_seq"])
        ml = row.get("machines_list")
        if isinstance(ml, list):
            out[(item, op_seq)] = [str(m) for m in ml]
        else:
            out[(item, op_seq)] = parse_machines(row.get("machines"))
    return out
