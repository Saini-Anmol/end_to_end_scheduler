"""Route 10 — visualisation (Section 10 #10, approach-flow step 26).

Thin orchestrator that calls writer_bom_graph + writer_gantt + writer_schedule.
Kept as a route so bootstrap can invoke it uniformly.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from V1.models.demand import DemandResult
from V1.models.schedule import ScheduleResult
from V1.reports import writer_bom_graph, writer_gantt, writer_schedule
from V1.utilities.bom_walker import BomGraph


def run(
    schedule: ScheduleResult,
    demand: DemandResult,
    bom: BomGraph,
    t0: datetime,
    output_dir: Path,
) -> dict[str, list[Path]]:
    """Render all viz outputs into `output_dir`. Returns a dict of artefact
    name → list of paths produced."""
    bom_path = writer_bom_graph.write(bom, output_dir)
    sched_paths = writer_schedule.write(schedule, t0, output_dir)
    gantt_paths = writer_gantt.write(schedule, demand, t0, output_dir)
    return {
        "bom_graph": [bom_path],
        "schedule": list(sched_paths),
        "gantt": gantt_paths,
    }
