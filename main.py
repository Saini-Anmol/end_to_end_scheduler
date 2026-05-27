#!/usr/bin/env python3
"""main.py — single-entry orchestrator for the JK Tyre BTP V1 scheduler.

Run `python main.py` (or `uv run python main.py`) from the project root to
execute the full pipeline end-to-end. All twelve route modules are invoked
in order by `V1.setups.bootstrap.run`; every Section 11 artefact lands in
a fresh `output/<HHMM-DD-MM-YYYY>/` folder:

    audit  →  audit_report.md, routing_cleaned.csv
    normalise + t0 auto-compute (CLAUDE.md L17)
    bom_graph
    demand_explosion
    lot_sizing
    graph_construction       →  dag.json
    backward_feasibility
    time_calculation
    forward_scheduler        →  reservation_log.csv
    diagnostics              →  aging_violations.csv, building_to_curing.csv,
                                infeasibilities.csv
    kpi                      →  kpi.csv
    visualisation            →  bom_graph.svg, gantt_all.html
    writer_excel             →  btp_schedule.xlsx   ← bundled workbook

The Excel workbook is the headline artefact — one sheet per tabular output
(`summary`, `kpi`, `schedule`, `machine_view`, `building_to_curing`,
`aging_violations`, `infeasibilities`, `reservation_log`, `routing_cleaned`,
`audit_halt`, `audit_warn`). The individual CSV/JSON/SVG/HTML files are
still written alongside it for downstream tooling.

Configuration (SKU code, t0 settings, Building primary, etc.) lives in
`V1/config/pilot.yaml`. CLI flags accepted for ad-hoc overrides:

    python main.py                     # defaults to ./input and ./output
    python main.py --inputs path/      # custom input folder
    python main.py --outputs path/     # custom output root

Exits 0 on success; non-zero on any HALT (see `V1/config/halt_codes.py`).
"""
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

# Ensure the repo root is on sys.path so `from V1...` resolves when this
# file is invoked directly via `python main.py` (without `uv run`).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from V1.setups.cli import main as _cli_main  # noqa: E402  (sys.path tweak above)


def main(argv: list[str] | None = None) -> int:
    """Run the whole pipeline and return the process exit code."""
    args = list(argv if argv is not None else sys.argv[1:])
    # Default --inputs to ./input next to this file when the user invokes
    # `python main.py` without arguments.
    if "--inputs" not in args:
        args.extend(["--inputs", str(PROJECT_ROOT / "input")])
    return _cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
