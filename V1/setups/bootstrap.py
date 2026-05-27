"""Pipeline orchestrator: wires routes 1 → 10 in order, honours HALT exit codes.

Pipeline order:
  1.  audit                    — HALT-capable (Section 9 findings)
  2.  unit_normalisation       — pure helper, no HALT
  3.  bom_graph                — pure helper, no HALT
  4.  demand_explosion
  5.  lot_sizing               — HALT-capable (Section 8.C)
  6.  graph_construction       — emits dag.json
  7.  backward_feasibility
  8.  time_calculation
  9.  forward_scheduler        — flag-and-continue (L11)
  10. diagnostics              — emits aging_violations + building_to_curing
  11. kpi
  12. visualisation            — bom_graph.svg + 1 master + 3 piece-wise Gantt HTMLs

Output artefacts land in `output/<HHMM-DD-MM-YYYY>/` (per pilot.yaml). The
folder is created up-front; on HALT we still flush the artefacts written so
far so the planner can inspect them.

Exit codes per V1.config.halt_codes.HaltCode.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from V1.config.halt_codes import HaltCode, HaltError
from V1.config.settings import Settings
from V1.reports import (
    writer_audit,
    writer_dag,
    writer_excel,
)
from V1.routes import (
    audit,
    backward_feasibility,
    demand_explosion,
    diagnostics,
    forward_scheduler,
    graph_construction,
    kpi,
    lot_sizing,
    time_calculation,
    visualisation,
)
from V1.setups.run_context import make_run_context
from V1.setups.t0_compute import compute_auto_t0
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


def run(
    settings: Settings,
    input_dir: Path,
    output_root: Path | None = None,
    now: datetime | None = None,
    curing_file: Path | None = None,
) -> int:
    """Run the pipeline. Returns the process exit code.

    `curing_file` (optional) overrides the default curing schedule path
    (`<input_dir>/BTP_PCR_May_Curing_Schedule.csv`). Accepts `.csv` or
    `.xlsx`.
    """
    ctx = make_run_context(
        settings, input_dir=input_dir, output_root=output_root, now=now
    )
    print(f"[run] run_id={ctx.run_id}  output_dir={ctx.output_dir}", flush=True)
    if curing_file is not None:
        print(f"[run] curing_override={curing_file}", flush=True)

    # 1. Audit
    audit_result = audit.run(ctx.input_dir, ctx.settings, curing_file=curing_file)
    # Skip the legacy routing_cleaned.csv standalone file — the bundled
    # btp_schedule.xlsx carries the same data on the `routing_cleaned` sheet.
    writer_audit.write(audit_result, ctx.output_dir, write_routing_csv=False)

    if audit_result.halt_findings:
        first = audit_result.halt_findings[0]
        code = audit.HALT_CODE_MAP.get(first.code, HaltCode.AUDIT_NULL_PROC_TIME)
        # Bundle whatever we have into the workbook before exiting.
        writer_excel.write_halt(
            audit=audit_result, settings=ctx.settings,
            t0=ctx.settings.t0_default, run_id=ctx.run_id,
            output_dir=ctx.output_dir,
        )
        print(
            f"[audit] HALT — {len(audit_result.halt_findings)} HALT finding(s), "
            f"{len(audit_result.warn_findings)} warning(s). "
            f"Binding: [{first.code}] {first.message}",
            flush=True,
        )
        return int(code)

    print(
        f"[audit] OK — {len(audit_result.warn_findings)} warning(s), "
        f"{len(audit_result.routing_cleaned_df)} cleaned routing rows.",
        flush=True,
    )

    # 2. Unit normalisation
    #    L17 auto-t0: anchor the run at the earliest feasible production
    #    start derived from the BOM critical path + aging + durations.
    t0_override = None
    if ctx.settings.t0_auto:
        t0_override, critical_path_min, sample_path = compute_auto_t0(
            audit_result, ctx.settings,
            safety_buffer_min=ctx.settings.t0_safety_buffer_min,
        )
        chain_str = " → ".join(reversed(sample_path)) if sample_path else "—"
        print(
            f"[t0_auto] critical_path={critical_path_min} min, "
            f"buffer={ctx.settings.t0_safety_buffer_min} min, "
            f"t0={t0_override.isoformat(sep=' ')}",
            flush=True,
        )
        print(f"[t0_auto] critical chain: {chain_str}", flush=True)
    norm = normalise(audit_result, ctx.settings, t0=t0_override)
    print(f"[normalise] t0={norm.t0}", flush=True)

    # 3. BOM graph
    bom = build_graph(
        norm.audit.bom_df, norm.aging_df, norm.audit.itemtype_df, ctx.settings
    )
    print(f"[bom_graph] {bom.graph.number_of_nodes()} nodes, "
          f"{bom.graph.number_of_edges()} edges", flush=True)

    # 4. Demand explosion
    demand = demand_explosion.run(norm, bom, ctx.settings)
    print(f"[demand_explosion] {len(demand.item_demands)} items, "
          f"{len(demand.block_demands)} block-demand rows", flush=True)

    # 5. Lot sizing
    try:
        lots = lot_sizing.run(norm, demand, ctx.settings)
    except HaltError as e:
        print(f"[lot_sizing] HALT — {e}", flush=True)
        return int(e.code)
    print(f"[lot_sizing] {len(lots.lots)} lots, "
          f"{len(lots.warnings)} under-min warning(s)", flush=True)

    # 6. Graph construction (lot DAG)
    dag = graph_construction.run(lots, bom, norm, ctx.settings)
    writer_dag.write(dag, ctx.output_dir)
    print(f"[graph_construction] {dag.node_count()} nodes, "
          f"{dag.edge_count()} edges", flush=True)

    # 7. Backward feasibility
    feas = backward_feasibility.run(lots, demand, bom, norm)

    # 8. Time calculation
    durs = time_calculation.run(lots, norm, ctx.settings)

    # 9. Forward scheduler
    sched = forward_scheduler.run(
        lots, demand, feas, durs, bom, norm, ctx.settings
    )
    print(f"[forward_scheduler] {len(sched.scheduled)} scheduled, "
          f"{len(sched.infeasibilities)} infeasibilities", flush=True)
    # Reservation log is materialised as a sheet inside btp_schedule.xlsx;
    # no standalone CSV is emitted.

    # 10. Diagnostics
    diag = diagnostics.run(sched, demand, norm, ctx.settings)
    # aging_violations + building_to_curing + infeasibilities ship as sheets
    # in btp_schedule.xlsx — no standalone CSVs.
    print(
        f"[diagnostics] aging_violations={len(diag.aging_violations)}, "
        f"building_to_curing={len(diag.building_to_curing)}",
        flush=True,
    )

    # 11. KPI
    kpi_result = kpi.run(sched, diag, lots)
    # KPI table lives on the `kpi` sheet of btp_schedule.xlsx; no kpi.csv.
    print(
        f"[kpi] OTIF={kpi_result.otif_pct:.1f}%, "
        f"processing={kpi_result.total_processing_min}min, "
        f"span={kpi_result.schedule_span_min}min",
        flush=True,
    )

    # 12. Visualisation
    visualisation.run(sched, demand, bom, norm.t0, ctx.output_dir)
    print("[viz] bom_graph.svg + gantt_all.html + gantt_part{1,2,3}.html", flush=True)

    # 13. Bundled Excel workbook — single file containing every tabular sheet.
    workbook_path = writer_excel.write_full(
        audit=audit_result, lots=lots, schedule=sched, diag=diag,
        kpi=kpi_result, settings=ctx.settings, t0=norm.t0,
        run_id=ctx.run_id, output_dir=ctx.output_dir,
    )
    print(f"[excel] {workbook_path.name}", flush=True)

    return int(HaltCode.OK)
