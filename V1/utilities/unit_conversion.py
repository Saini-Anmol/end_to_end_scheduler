"""Unit conversion (L20) — single source of truth.

Aging units → minutes:  Days × 1440, Hours × 60, Minutes × 1, with `Min` and
`Hr/Hrs/Hour/Day` accepted as aliases observed in the live Aging Master.

Routing proc_time UOMs:
  - SEC/BATCH, SEC → ceil(proc_time / 60) minutes
  - MIN           → ceil(proc_time) minutes
  - M/MIN         → DEFERRED to time_calculation (needs lot_qty)

Single ceil rounding direction. Duplicating ceil(x/60) outside this module is
a defect (L23).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from V1.config.settings import Settings
from V1.routes.audit import AuditResult
from V1.utilities.time_math import ceil_div, to_minute


# Accepted aging-unit aliases. Keys are case-insensitive.
_AGING_UNIT_MULT_MIN: dict[str, int] = {
    "minutes": 1, "minute": 1, "min": 1,
    "hours": 60, "hour": 60, "hr": 60, "hrs": 60,
    "days": 1440, "day": 1440,
}


def aging_to_minutes(value: object, unit: object) -> Optional[int]:
    """Convert (value, unit) → integer minutes with ceil rounding.

    Returns None when value/unit is missing or the unit is not in the
    recognised set. Module 3 (BOM graph builder) HALTs if any in-scope
    item ends up with None aging after this pass.
    """
    if value is None or unit is None:
        return None
    try:
        if pd.isna(value) or pd.isna(unit):
            return None
    except TypeError:
        pass
    mult = _AGING_UNIT_MULT_MIN.get(str(unit).strip().lower())
    if mult is None:
        return None
    return int(math.ceil(float(value) * mult))


def convert_qty(
    value: float,
    from_uom: str,
    to_uom: str,
    bom_output_qty: float | None = None,
    bom_output_uom: str | None = None,
) -> float:
    """Convert `value` from `from_uom` to `to_uom`.

    Handles:
      - Same UOM → identity.
      - MTR ↔ MM (factor 1000).
      - NOS → MM via the item's BOM output_qty (1 NOS = output_qty if
        bom_output_uom is MM). The reverse (MM → NOS) divides by output_qty.

    Raises ValueError when the conversion is undefined for V1.
    """
    fn = _norm_uom(from_uom)
    tn = _norm_uom(to_uom)
    if fn == tn:
        return float(value)
    # MTR ↔ MM
    if fn == "MTR" and tn == "MM":
        return float(value) * 1000.0
    if fn == "MM" and tn == "MTR":
        return float(value) / 1000.0
    # NOS ↔ MM via output_qty
    if {fn, tn} == {"NOS", "MM"}:
        if bom_output_qty is None or _norm_uom(bom_output_uom or "") != "MM":
            raise ValueError(
                f"NOS↔MM conversion requires bom_output_qty in MM (got "
                f"{bom_output_qty!r} {bom_output_uom!r})"
            )
        if fn == "NOS":
            return float(value) * float(bom_output_qty)
        return float(value) / float(bom_output_qty)
    raise ValueError(f"Unsupported UOM conversion: {from_uom!r} → {to_uom!r}")


_UOM_ALIASES: dict[str, str] = {
    "M": "MTR",
    "MTRS": "MTR",
    "METER": "MTR",
    "METRE": "MTR",
    "METERS": "MTR",
    "METRES": "MTR",
    "MM": "MM",
    "KGS": "KG",
    "NOS": "NOS",
    "PCS": "NOS",
    "NO": "NOS",
}


def _norm_uom(uom: str) -> str:
    """Case- and whitespace-normalise a UOM string + alias common spellings.

    'Nos'/'NOS'/'nos'/'PCS' → 'NOS'; 'M'/'Meter' → 'MTR'; 'MTR / Nos' →
    'MTR' (first token).
    """
    s = (uom or "").strip()
    if "/" in s:
        s = s.split("/", 1)[0].strip()
    s = s.upper()
    return _UOM_ALIASES.get(s, s)


def proc_time_to_minutes(proc_time: object, uom: object) -> Optional[int]:
    """Convert (proc_time, uom) → integer minutes for static UOMs (L20).

    Returns None for M/MIN — that conversion needs the lot's running length
    and lives in time_calculation. None is also returned for missing or
    unknown UOMs.
    """
    if proc_time is None or uom is None:
        return None
    try:
        if pd.isna(proc_time) or pd.isna(uom):
            return None
    except TypeError:
        pass
    u = str(uom).strip()
    pt = float(proc_time)
    if u in ("SEC/BATCH", "SEC"):
        return ceil_div(pt, 60)
    if u == "MIN":
        return int(math.ceil(pt))
    if u == "M/MIN":
        return None
    return None


# --- Orchestration ---------------------------------------------------------


@dataclass
class NormalisedResult:
    """AuditResult + minute-domain columns + t0 anchor.

    Frames are *copies* of the AuditResult frames with new columns added.
    The original AuditResult is left untouched (pure function).

    New columns:
      - aging_df:    min_aging_min (Int64|NA), max_aging_min (Int64|NA)
      - routing_df:  proc_time_min (Int64|NA; NA for M/MIN — per-lot)
      - curing_df:   start_min, end_min (int minutes since t0)
    """
    audit: AuditResult
    t0: datetime
    aging_df: pd.DataFrame
    routing_df: pd.DataFrame
    curing_df: pd.DataFrame


def normalise(audit_result: AuditResult, settings: Settings,
              t0: datetime | None = None) -> NormalisedResult:
    """Apply L20 conversions to the audit frames. Returns a new result."""
    t0_use = t0 or settings.t0_default

    aging = audit_result.aging_df.copy()
    aging["min_aging_min"] = [
        aging_to_minutes(v, u)
        for v, u in zip(aging["MinAging"], aging["MinAgingUnit"])
    ]
    aging["max_aging_min"] = [
        aging_to_minutes(v, u)
        for v, u in zip(aging["MaxAging"], aging["MaxAgingUnit"])
    ]

    routing = audit_result.routing_cleaned_df.copy()
    routing["proc_time_min"] = [
        proc_time_to_minutes(pt, u)
        for pt, u in zip(routing["proc_time"], routing["proc_time_UOM"])
    ]

    curing = audit_result.curing_df.copy()
    curing["start_min"] = [to_minute(t, t0_use) for t in curing["StartTime"]]
    curing["end_min"] = [to_minute(t, t0_use) for t in curing["EndTime"]]

    return NormalisedResult(
        audit=audit_result, t0=t0_use,
        aging_df=aging, routing_df=routing, curing_df=curing,
    )
