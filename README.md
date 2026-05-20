# JK Tyre BTP — Forward Production Scheduler (V1)

Deterministic, BOM-driven forward production scheduler for the JK Tyre
Banmore Tyre Plant (BTP) pilot SKU `1325220516095HTMX0` (205/65 R16 PCR).
V1 scope is **demand fulfilment only** — see `CLAUDE.md` Section 1.5 for
the explicit V1 vs V2 split.

The authoritative project brief, all 23 locked decisions (L1–L23), and the
26-step approach flow live in `CLAUDE.md`. The methodology write-up
(architecture, fixture pass evidence, acceptance against Section 12) lives
in `docs/methodology.md`.

## Run

```
uv sync --extra dev --extra viz
uv run python -m V1.setups.cli --inputs input/
```

On the vanilla pilot inputs the audit HALTs at exit code **10**
(`AUDIT_NULL_PROC_TIME`) because routing row 61 — `BD-12843443-4 AUTO AND
MANUAL FILLERING` — has a null `proc_time`. This is the expected behaviour
per Section 8.D ("no silent imputation"). `audit_report.md` is still
written so the planner can see the binding finding before supplying a
value.

To exercise the **full** pipeline end-to-end on the pilot data, supply the
Fillering `proc_time`. Either:

- Edit the routing xlsx in `input/` and re-run, **or**
- Use the integration-test path that patches one row in a copy of the
  inputs: `uv run pytest tests/integration -v`

## Tests

```
uv run pytest tests -q
```

**215 tests** (209 unit + 6 integration). The integration suite includes
byte-identical re-run verification per L11 / Section 12.2.

## Layout

```
.
├── CLAUDE.md                # Authoritative project brief (read first)
├── input/                   # Raw inputs — never modified
│   ├── BTP_PCR_May_Curing_Schedule.csv
│   ├── BTP_Routing_…BOM_Final (1).xlsx
│   └── JKT_BTP_Forward_Scheduler_Problem_Statement.pdf
├── output/<HHMM-DD-MM-YYYY>/   # One dated folder per run, never overwritten
│   ├── audit_report.md
│   ├── routing_cleaned.csv
│   ├── schedule.csv
│   ├── machine_view.csv
│   ├── building_to_curing.csv
│   ├── aging_violations.csv
│   ├── infeasibilities.csv
│   ├── reservation_log.csv
│   ├── kpi.csv
│   ├── dag.json
│   ├── bom_graph.svg
│   └── gantt_<block>.html
├── V1/
│   ├── config/              # pilot.yaml + settings/constants/enums/halt_codes
│   ├── models/              # Frozen dataclasses (Lot, ScheduledLot, …)
│   ├── routes/              # 12 pipeline modules
│   ├── utilities/           # Pure helpers (time math, FEFO, BOM walker, …)
│   ├── reports/             # Output writers — datetime↔minute boundary
│   └── setups/              # CLI, run context, bootstrap
├── tests/
│   ├── fixtures/            # 5 golden Section 17 cases
│   ├── unit/                # 209 unit tests
│   └── integration/         # 6 end-to-end + byte-identical re-run tests
└── docs/
    └── methodology.md       # Approach, decisions, fixture coverage,
                             # V1 vs V2 limitations, Section 12 acceptance
```

## Key outputs (Section 11)

| Artefact | Purpose |
|---|---|
| `schedule.csv` | Lot-level schedule: `lot_id, item_code, machine_id, start_min, end_min, qty, uom, serves_blocks, start_dt, end_dt` |
| `machine_view.csv` | Same rows sorted by `machine_id` + `start_min` |
| `building_to_curing.csv` | Per Building (GT) lot — OK / LATE / EARLY classification |
| `aging_violations.csv` | One row per breached BOM edge, with `violation_type` (MIN / MAX) |
| `infeasibilities.csv` | One row per unschedulable lot with the binding constraint named |
| `reservation_log.csv` | Per Section 16 schema — created / consumed / expired / released events |
| `kpi.csv` | Totals, OTIF %, processing min, span, per-machine utilisation |
| `dag.json` | Machine-readable lot dependency graph (nodes + edges with aging windows) |
| `bom_graph.svg` | BOM tree viz (Capstrip subtree tagged OUT-OF-SCOPE per L12) |
| `gantt_<block>.html` | Plotly Gantt for the early/middle/late sample blocks |
| `audit_report.md` | Section 9 findings split into HALT vs WARN buckets |
| `routing_cleaned.csv` | Routing after dedup + Capstrip drop + machine-list normalisation |
```

## Determinism guarantees (L11 / Section 12.2)

- All iteration orders sorted explicitly.
- Single `ceil` rounding direction everywhere (L20).
- No `random`, no wall-clock-dependent defaults.
- Datetime ↔ minute conversion confined to one entry boundary (`audit` /
  `unit_normalisation`) and one exit boundary (writers).
- `machine_id` carried as `str` end-to-end so leading zeros (`0201`, `0202`,
  …) are never coerced to int (L23).

The integration test `test_deterministic_artefacts_byte_identical` re-runs
the pipeline twice and asserts byte-identical output for the 9 deterministic
files.
