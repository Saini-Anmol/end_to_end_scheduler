"""Compute the earliest feasible `t0` from BOM depth + aging + duration data.

CLAUDE.md L17 originally placed t0 behind a config placeholder ("DEFERRED").
This module implements the L2-derived auto-t0:

    t0 = first_curing_start − critical_path − safety_buffer

where `critical_path` is the longest sum of (per-item production duration +
per-item min_aging) along any leaf → SKU walk through the BOM. The
"safety_buffer" defaults to 60 minutes and is configurable.

The duration estimate is BOM-level (no lot data needed): for each item that
has a routing row, simulate one curing block's worth of production (64
tyres × per-tyre qty walked from the BOM) using the same UOM rules as
`time_calculation._nominal_min`. Raws and Work-Away items contribute 0.

This is a single-pass approximation. Actual durations may differ for very
large MPQ_Max-bounded lots, but the result is conservative because the
buffer accounts for routine slack.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

import networkx as nx
import pandas as pd

from V1.config.settings import Settings
from V1.routes.audit import AuditResult
from V1.utilities.time_math import ceil_div
from V1.utilities.unit_conversion import _norm_uom, aging_to_minutes, convert_qty


_BUILDING_OP_NAMES = frozenset({"vmimaxx group"})
_BUILDING_DEPTS = frozenset({"building"})


def _per_tyre_qty(
    bom_df: pd.DataFrame, sku: str, capstrip_items: set[str],
) -> dict[str, float]:
    """BFS down the BOM from SKU, computing per-tyre consumption per item."""
    per_tyre: dict[str, float] = {sku: 1.0}
    bom_by_output: dict[str, list] = {}
    for _, row in bom_df.iterrows():
        bom_by_output.setdefault(str(row["Output"]), []).append(row)
    visited: set[str] = {sku}
    queue: list[str] = [sku]
    while queue:
        parent = queue.pop()
        parent_qty = per_tyre.get(parent, 0.0)
        if parent_qty <= 0:
            continue
        for row in bom_by_output.get(parent, []):
            child = str(row["input code"])
            if child in capstrip_items or parent in capstrip_items:
                continue
            input_qty = float(row["qty"]) if pd.notna(row.get("qty")) else 0.0
            output_qty = float(row["output qty"]) if pd.notna(row.get("output qty")) else 1.0
            if output_qty <= 0:
                continue
            contribution = parent_qty * input_qty / output_qty
            per_tyre[child] = per_tyre.get(child, 0.0) + contribution
            if child not in visited:
                visited.add(child)
                queue.append(child)
    return per_tyre


def _per_tyre_uom(bom_df: pd.DataFrame) -> dict[str, str]:
    """Natural UOM per item — input UOM (unit.1) where it's a child, else
    output UOM (unit) where it's an Output."""
    uom: dict[str, str] = {}
    for _, row in bom_df.iterrows():
        child = str(row["input code"])
        u = row.get("unit.1")
        if pd.notna(u) and child not in uom:
            uom[child] = str(u)
    for _, row in bom_df.iterrows():
        out = str(row["Output"])
        u = row.get("unit")
        if pd.notna(u) and out not in uom:
            uom[out] = str(u)
    return uom


def _bom_output_qty_uom(
    bom_df: pd.DataFrame,
) -> dict[str, tuple[Optional[float], Optional[str]]]:
    """Per-item BOM Output rate (output qty + unit) — used for NOS↔MM
    conversion in duration estimates."""
    out: dict[str, tuple[Optional[float], Optional[str]]] = {}
    for _, row in bom_df.iterrows():
        item = str(row["Output"])
        if item in out:
            continue
        qty = float(row["output qty"]) if pd.notna(row.get("output qty")) else None
        unit = str(row["unit"]) if pd.notna(row.get("unit")) else None
        out[item] = (qty, unit)
    return out


def _estimate_item_duration(
    routing_row: pd.Series, per_tyre_qty: float, per_tyre_uom: str,
    bom_output_qty: Optional[float], bom_output_uom: Optional[str],
    settings: Settings, tyres_per_block: int = 64,
) -> int:
    """Estimate effective minutes for one curing block's production of this
    item — uses the SAME rules as time_calculation._nominal_min."""
    proc_time_raw = routing_row.get("proc_time")
    if proc_time_raw is None or pd.isna(proc_time_raw) or float(proc_time_raw) <= 0:
        return 0
    proc_time = float(proc_time_raw)
    proc_uom = str(routing_row["proc_time_UOM"]).strip()
    batch_size_raw = routing_row.get("batch_size")
    batch_size = (float(batch_size_raw)
                  if pd.notna(batch_size_raw) and float(batch_size_raw) > 0 else None)
    batch_unit = (str(routing_row["batch_UNIT"])
                  if pd.notna(routing_row.get("batch_UNIT")) else None)

    per_block_qty = tyres_per_block * per_tyre_qty
    if per_block_qty <= 0:
        return 0

    op = str(routing_row.get("operation_name", "")).strip().lower()
    dept = str(routing_row.get("department", "")).strip().lower()
    is_building = op in _BUILDING_OP_NAMES or dept in _BUILDING_DEPTS

    try:
        if proc_uom == "M/MIN":
            qty_mtr = convert_qty(per_block_qty, per_tyre_uom, "MTR",
                                  bom_output_qty=bom_output_qty,
                                  bom_output_uom=bom_output_uom)
            nominal = math.ceil(qty_mtr / proc_time)
        elif batch_size is not None and batch_unit:
            qty_in_batch = convert_qty(per_block_qty, per_tyre_uom, batch_unit,
                                       bom_output_qty=bom_output_qty,
                                       bom_output_uom=bom_output_uom)
            n_batches = max(1, math.ceil(qty_in_batch / batch_size))
            if proc_uom in ("SEC/BATCH", "SEC"):
                per_batch = ceil_div(proc_time, 60)
            elif proc_uom == "MIN":
                per_batch = int(math.ceil(proc_time))
            else:
                return 0
            nominal = n_batches * per_batch
        else:
            cycle_size = settings.building_tyres_per_cycle if is_building else 1
            if bom_output_qty and bom_output_qty > 0 and (
                _norm_uom(per_tyre_uom) == _norm_uom(bom_output_uom or per_tyre_uom)
            ):
                n_units = per_block_qty / bom_output_qty
            else:
                n_units = per_block_qty
            n_cycles = max(1, math.ceil(n_units / cycle_size))
            if proc_uom in ("SEC/BATCH", "SEC"):
                per_cycle = ceil_div(proc_time, 60)
            elif proc_uom == "MIN":
                per_cycle = int(math.ceil(proc_time))
            else:
                return 0
            nominal = n_cycles * per_cycle
    except ValueError:
        # Conservative fallback for UOM combinations we don't handle.
        return 0

    return int(math.ceil(nominal / settings.efficiency_factor))


def _scoped_bom_graph(bom_df: pd.DataFrame, capstrip_items: set[str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for _, row in bom_df.iterrows():
        parent = str(row["Output"])
        child = str(row["input code"])
        if parent in capstrip_items or child in capstrip_items:
            continue
        g.add_edge(parent, child)
    return g


def _critical_path_minutes(
    durations: dict[str, int], aging_min: dict[str, int],
    sku: str, bom_df: pd.DataFrame, capstrip_items: set[str],
) -> tuple[int, list[str]]:
    """Longest path through the BOM from any node to SKU summing
    (own_duration + own_min_aging). Returns (minutes, sample_path)."""
    g = _scoped_bom_graph(bom_df, capstrip_items)
    if sku not in g:
        return 0, []

    # DP: cp[item] = own_time + max over consumers (cp[consumer]); cp[sku] = 0.
    cp: dict[str, int] = {sku: 0}
    predecessor: dict[str, Optional[str]] = {sku: None}
    # Iterate consumers-first (parents-first in original graph edge direction).
    topo = list(nx.lexicographical_topological_sort(g))
    for item in topo:
        if item == sku:
            continue
        consumers = list(g.predecessors(item))
        best_consumer = None
        best_consumer_cp = 0
        for c in consumers:
            if c in cp and cp[c] >= best_consumer_cp:
                best_consumer = c
                best_consumer_cp = cp[c]
        own_time = durations.get(item, 0) + aging_min.get(item, 0)
        cp[item] = best_consumer_cp + own_time
        predecessor[item] = best_consumer

    # Identify the critical-path tail
    if not cp:
        return 0, []
    max_node = max(cp, key=lambda n: cp[n])
    path: list[str] = []
    cursor: Optional[str] = max_node
    while cursor is not None:
        path.append(cursor)
        cursor = predecessor.get(cursor)
    return cp[max_node], path


def compute_auto_t0(
    audit_result: AuditResult,
    settings: Settings,
    safety_buffer_min: int = 60,
    tyres_per_block: int = 64,
) -> tuple[datetime, int, list[str]]:
    """Return (t0, critical_path_min, sample_critical_path) for the pilot.

    The returned t0 anchors the run such that even the longest BOM chain
    can reach the first curing block on time, with `safety_buffer_min` of
    slack.
    """
    cap = set(settings.capstrip_items)
    bom = audit_result.bom_df
    routing = audit_result.routing_cleaned_df
    aging = audit_result.aging_df

    first_curing_dt = pd.Timestamp(audit_result.curing_df.iloc[0]["StartTime"]).to_pydatetime()

    per_tyre = _per_tyre_qty(bom, settings.sku_code, cap)
    per_tyre_uom_map = _per_tyre_uom(bom)
    bom_output_map = _bom_output_qty_uom(bom)

    aging_min: dict[str, int] = {}
    for _, row in aging.iterrows():
        v = aging_to_minutes(row.get("MinAging"), row.get("MinAgingUnit"))
        if v is not None:
            aging_min[str(row["ItemCode"])] = v

    items_in_bom: set[str] = set()
    for _, row in bom.iterrows():
        items_in_bom.add(str(row["Output"]))
        items_in_bom.add(str(row["input code"]))

    durations: dict[str, int] = {}
    for item in items_in_bom:
        if item == settings.sku_code or item in cap:
            continue
        rows = routing[routing["routed_product"] == item]
        if len(rows) == 0:
            durations[item] = 0
            continue
        out_qty, out_uom = bom_output_map.get(item, (None, None))
        durations[item] = _estimate_item_duration(
            rows.iloc[0],
            per_tyre.get(item, 0.0),
            per_tyre_uom_map.get(item, "NOS"),
            out_qty, out_uom, settings, tyres_per_block,
        )

    critical_path_min, sample_path = _critical_path_minutes(
        durations, aging_min, settings.sku_code, bom, cap,
    )

    t0 = first_curing_dt - timedelta(
        minutes=critical_path_min + safety_buffer_min
    )
    # Round down to the nearest minute for clean wall-clock anchoring.
    t0 = t0.replace(second=0, microsecond=0)
    return t0, critical_path_min, sample_path
