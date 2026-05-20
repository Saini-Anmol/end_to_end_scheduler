"""KPI records — output of Module 12 (kpi)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MachineUtilisation:
    machine_id: str
    busy_min: int
    span_min: int
    utilisation_pct: float        # busy_min / span_min × 100


@dataclass
class KpiResult:
    # Counts
    total_lots_scheduled: int
    total_lots_infeasible: int
    total_warnings: int
    # Building → Curing
    building_lots_ok: int
    building_lots_late: int
    building_lots_early: int
    otif_pct: float
    # Aging
    aging_violations_total: int
    aging_violations_min: int
    aging_violations_max: int
    # Time
    total_processing_min: int
    changeover_min: int           # 0 in V1 (L8)
    schedule_span_min: int        # max(end) - min(start) of scheduled lots
    # Per-machine utilisation
    machines: list[MachineUtilisation] = field(default_factory=list)
