"""Route 9 — kpi (Section 10 #9, approach-flow step 25).

Computes the headline KPIs: total lots, OTIF % at the Building→Curing
handoff, total processing minutes, changeover minutes (0 in V1 per L8),
schedule span, per-machine utilisation.

OTIF denominator (V1): the number of Building→Curing records produced by
diagnostics (one per committed Building lot per served block). If no
Building lots committed (e.g. cascading from BD-12843443-4 Fillering HALT),
OTIF is undefined → reported as 0.0.
"""
from __future__ import annotations

from collections import defaultdict

from V1.models.diagnostics import DiagnosticsResult
from V1.models.kpi import KpiResult, MachineUtilisation
from V1.models.lot import LotsResult
from V1.models.schedule import ScheduleResult


def run(
    schedule: ScheduleResult,
    diag: DiagnosticsResult,
    lots: LotsResult,
) -> KpiResult:
    scheduled = schedule.scheduled

    # OTIF
    btc = diag.building_to_curing
    n_ok = sum(1 for r in btc if r.classification == "OK")
    n_late = sum(1 for r in btc if r.classification == "LATE")
    n_early = sum(1 for r in btc if r.classification == "EARLY")
    otif_pct = (100.0 * n_ok / len(btc)) if btc else 0.0

    # Aging violations
    n_av = len(diag.aging_violations)
    n_av_min = sum(1 for v in diag.aging_violations if v.violation_type == "MIN")
    n_av_max = sum(1 for v in diag.aging_violations if v.violation_type == "MAX")

    # Time aggregates
    total_proc = sum(s.duration_min for s in scheduled)
    if scheduled:
        span = max(s.end_min for s in scheduled) - min(s.start_min for s in scheduled)
    else:
        span = 0

    # Per-machine utilisation
    busy_per_machine: dict[str, int] = defaultdict(int)
    earliest_per_machine: dict[str, int] = {}
    latest_per_machine: dict[str, int] = {}
    for s in scheduled:
        busy_per_machine[s.machine_id] += s.duration_min
        earliest_per_machine.setdefault(s.machine_id, s.start_min)
        earliest_per_machine[s.machine_id] = min(
            earliest_per_machine[s.machine_id], s.start_min
        )
        latest_per_machine[s.machine_id] = max(
            latest_per_machine.get(s.machine_id, s.end_min), s.end_min
        )
    machine_records: list[MachineUtilisation] = []
    for m in sorted(busy_per_machine):
        m_span = latest_per_machine[m] - earliest_per_machine[m]
        util = (100.0 * busy_per_machine[m] / m_span) if m_span > 0 else 0.0
        machine_records.append(MachineUtilisation(
            machine_id=m, busy_min=busy_per_machine[m],
            span_min=m_span, utilisation_pct=util,
        ))

    return KpiResult(
        total_lots_scheduled=len(scheduled),
        total_lots_infeasible=len(schedule.infeasibilities),
        total_warnings=len(lots.warnings),
        building_lots_ok=n_ok,
        building_lots_late=n_late,
        building_lots_early=n_early,
        otif_pct=otif_pct,
        aging_violations_total=n_av,
        aging_violations_min=n_av_min,
        aging_violations_max=n_av_max,
        total_processing_min=total_proc,
        changeover_min=0,                # V1 — see L8
        schedule_span_min=span,
        machines=machine_records,
    )
