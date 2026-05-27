"""Route 10 — visualisation (Section 10 #10, approach-flow step 26).

Thin orchestrator that calls writer_bom_graph + writer_gantt. Emits the BOM
diagram plus FOUR Gantt HTMLs: one master view (`gantt_all.html`) covering
every machine across the full horizon, and three piece-wise views
(`gantt_part1.html`, `gantt_part2.html`, `gantt_part3.html`) each
covering a third of the schedule's time range for legibility. The
lot-level schedule + machine view live as sheets inside
`btp_schedule.xlsx` (written by writer_excel); no standalone schedule.csv
/ machine_view.csv is produced.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from V1.models.demand import DemandResult
from V1.models.schedule import ScheduleResult
from V1.reports import writer_bom_graph, writer_gantt
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
    gantt_paths = writer_gantt.write(schedule, demand, t0, output_dir)
    return {
        "bom_graph": [bom_path],
        "gantt": gantt_paths,
    }
