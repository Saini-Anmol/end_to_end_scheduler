# JK Tyre BTP — Forward Production Scheduler

**Deterministic, BOM-driven forward production scheduler for the JK Tyre Banmore Tyre Plant (BTP) — Passenger-Car Radial pilot SKU `1325220516095HTMX0`.**

The engine takes the published May curing schedule as a **fixed input** and produces a fully time-stamped, machine-assigned schedule for every upstream operation — Mixing, Final Mixing, Calendering, Cutting, Ply Cutting, Bead Building, Extrusion, and Tyre Building. Curing is never moved; if upstream cannot feed it, the engine flags the violation and continues.

This is the **V1 build**, scoped to **demand fulfilment only**. The KPIs that matter in V1 are OTIF % at the Building → Curing handoff, count of aging violations, count of infeasibilities, and coverage. Changeover modelling and utilisation optimisation are deferred to V2.

The authoritative project brief — all 23 locked design decisions (L1–L23), the 26-step approach flow, the 5 golden fixtures, and the standing assumptions — lives in [CLAUDE.md](CLAUDE.md). The methodology write-up (architecture, evidence, acceptance against the problem-statement criteria) lives in [docs/methodology.md](docs/methodology.md).

---

## Contents

- [Pilot SKU and horizon](#pilot-sku-and-horizon)
- [Quick start](#quick-start)
- [Inputs](#inputs)
- [Outputs](#outputs)
- [Pipeline architecture](#pipeline-architecture)
- [Configuration](#configuration)
- [Determinism guarantees](#determinism-guarantees)
- [HALT exit codes](#halt-exit-codes)
- [Testing](#testing)
- [Project layout](#project-layout)
- [V1 scope and known simplifications](#v1-scope-and-known-simplifications)
- [References](#references)

---

## Pilot SKU and horizon

| Attribute | Value |
|---|---|
| SKU code | `1325220516095HTMX0` |
| Description | 205/65 R16 Passenger-Car Radial (Taxi MX TL) |
| Green tyre | `GT2056516TAXIMXTL` — 8 in-scope BOM children (Capstrip out of scope, L12) |
| Curing press | `14811` (fixed input, immovable per L4.5) |
| Horizon | 2026-05-17 06:49 → 2026-05-30 22:19 (~14 days) |
| Curing blocks | 42 (mostly 64 tyres / 8-hr shift, 15-min press cycle) |
| Total demand | 2,620 tyres |
| Starting GT inventory | 0 on every row |
| BOM depth | 7 levels (SKU → Green Tyre → component → sub-component → final compound → master compound → raw) |

---

## Quick start

### Prerequisites

- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv) (or any PEP-517-compatible installer)

### Install

```bash
uv sync --extra dev --extra viz
```

`dev` brings in `pytest` and `pytest-cov`. `viz` brings in `matplotlib`, `plotly`, and `graphviz` for the BOM graph and Gantt outputs.

### Run end-to-end

```bash
uv run python -m V1.setups.cli --inputs input/
```

Or via the installed console script:

```bash
uv run btp-scheduler --inputs input/
```

### Expected behaviour on the vanilla pilot inputs

The audit module HALTs at exit code **10** (`AUDIT_NULL_PROC_TIME`) because routing row 61 — `BD-12843443-4 AUTO AND MANUAL FILLERING` — has a null `proc_time`. This is the correct behaviour per CLAUDE.md §8.D: **no silent imputation**. The engine writes `audit_report.md` and `routing_cleaned.csv` so the planner can inspect the binding finding before supplying a value.

### Running the full pipeline end-to-end

Supply a value for the Fillering `proc_time`. Two options:

1. Edit the routing Excel in `input/` and re-run.
2. Use the integration test path, which patches a copy of the inputs in a temporary folder and runs the full chain twice (asserting byte-identical re-runs):

   ```bash
   uv run pytest tests/integration -v
   ```

---

## Inputs

Place all three files in `input/`. The engine treats them as **read-only**; it never modifies the originals.

| File | Purpose |
|---|---|
| `BTP_PCR_May_Curing_Schedule.csv` | 14,292 rows over the full May plan; 42 rows for the pilot SKU. Each pilot row is a non-negotiable demand event. Columns: `Date, Shift, Machine, SKUCode, StartTime, EndTime, Qty, CycleTime_min, GT_Inventory, Remarks, SKU_Description`. |
| `BTP_Routing_1325216614081STMX0 BOM_Final (1).xlsx` | Six sheets — `BOM - <sku>`, `Routing - <sku>`, `Aging Master`, `Buffer Master` (ignored per L4), `ItemType Master`, `MPQ`. |
| `JKT_BTP_Forward_Scheduler_Problem_Statement.pdf` | Authoritative problem definition. Section numbers cited in `CLAUDE.md` resolve into this document. |

The audit module surfaces every data-quality finding it sees, classified as **HALT** or **WARN** per CLAUDE.md §9. WARN findings are logged and the pipeline continues; HALT findings stop the run before any `schedule.csv` is written.

---

## Outputs

Every run creates a fresh dated folder `output/<HHMM-DD-MM-YYYY>/`. Folders are never overwritten across runs — re-running within the same minute raises `FileExistsError` (deliberate).

| Artefact | Content |
|---|---|
| `audit_report.md` | Section 9 findings, split into HALT vs WARN buckets, with sheet / row citations. Written on every run, including HALTs. |
| `routing_cleaned.csv` | Routing after dedup (L7), Capstrip drop (L12), and machine-list normalisation (§8.F — adds derived `eligible_machine_count`). |
| `schedule.csv` | Lot-level schedule. Columns: `lot_id, item_code, item_type, op_seq, machine_id, start_min, end_min, duration_min, qty, uom, serves_blocks, start_dt, end_dt`. |
| `machine_view.csv` | Same rows sorted by `(machine_id, start_min, lot_id)` for floor-level execution. |
| `building_to_curing.csv` | One row per Building (GT) lot per served block. Classification = `OK` / `LATE` / `EARLY` with delta minutes against the curing block start. |
| `aging_violations.csv` | One row per breached consumer-producer pair: `consumer_lot, predecessor_lot, item_code, edge_min, edge_max, actual_gap, violation_type` (MIN or MAX). |
| `infeasibilities.csv` | One row per unschedulable lot with the binding constraint named (`AND_JOIN`, `BLOCK_OVERLAP`, `AGING`, `MACHINE`, `DURATION`, `DEADLINE`). |
| `reservation_log.csv` | Per CLAUDE.md §16: `event_minute, event_type, consumer_lot_id, producer_lot_id, item_code, qty, producer_end_min, latest_acceptable_start_min`. |
| `kpi.csv` | Totals (lots scheduled / infeasible / warnings), OTIF %, aging-violation breakdown, processing minutes, schedule span, per-machine utilisation. |
| `dag.json` | Machine-readable lot dependency graph — nodes + edges with aging windows and effective-gap minutes. |
| `bom_graph.svg` | Static BOM tree viz. Capstrip subtree appears tagged "OUT-OF-SCOPE — awaiting data". |
| `gantt_<block>.html` | Plotly Gantt for three sample blocks — earliest, middle, latest in the horizon. |
| **`btp_schedule.xlsx`** | **Bundled workbook — single file with one sheet per tabular artefact (`summary`, `kpi`, `schedule`, `machine_view`, `building_to_curing`, `aging_violations`, `infeasibilities`, `reservation_log`, `routing_cleaned`, `audit_halt`, `audit_warn`). The headline artefact the planner opens.** On HALT runs, a slimmed-down version is written with `summary`, `audit_halt`, `audit_warn`, and `routing_cleaned` only. |

**HALT runs** skip `schedule.csv` and every downstream artefact. `audit_report.md` and `routing_cleaned.csv` are always written.

---

## Pipeline architecture

Twelve modules, each runnable in isolation. Orchestrated by [V1/setups/bootstrap.py](V1/setups/bootstrap.py). Module boundaries follow CLAUDE.md §10 / §15.

| # | Module | Purpose |
|---|---|---|
| 1 | [`audit`](V1/routes/audit.py) | Read raw inputs; surface data-quality findings; dedup masters; parse messy machine cells; drop Capstrip (L12) and the EHT1000 NaN-is_primary row (L7). HALT-capable. |
| 2 | [`unit_normalisation`](V1/utilities/unit_conversion.py) | Convert aging Days / Hours / Minutes → integer minutes; convert routing `proc_time` SEC/BATCH, MIN → minutes via `ceil(x/60)`; anchor curing datetimes to `t0`. Single ceil rounding direction throughout (L20). |
| 3 | [`bom_graph`](V1/utilities/bom_walker.py) | Build an `nx.DiGraph` from the BOM; propagate `is_capstrip` down from the configured seeds; validate acyclicity. |
| 4 | [`demand_explosion`](V1/routes/demand_explosion.py) | Walk the BOM per curing block: `child_qty = parent_qty × (edge.qty / edge.output_qty)`. Aggregate per item; preserve `serves_blocks` chronologically. |
| 5 | [`lot_sizing`](V1/routes/lot_sizing.py) | Forward-aggregate consecutive block demands into the largest lot satisfying both `qty ≤ MPQ_Max` and `curing-span ≤ (aging_MAX − aging_MIN)`. Equal-split when a single block exceeds `MPQ_Max`. **HALT** when a single-block lot < `MPQ_Min` AND is aging-isolated from all other demand (§8.C). |
| 6 | [`graph_construction`](V1/routes/graph_construction.py) | Build the lot-level DAG; attach `effective_gap = MAX(transfer, MIN_aging)` per edge (L14). Emit `dag.json`. |
| 7 | [`backward_feasibility`](V1/routes/backward_feasibility.py) | Per-lot `latest_acceptable_end_min` from the min-aging chain to the SKU. Pure feasibility limit — no time commitment. |
| 8 | [`time_calculation`](V1/routes/time_calculation.py) | Per `(lot, eligible_machine)`: `duration_min = ceil(nominal_min / 0.95)` (L10 / L20). |
| 9 | [`forward_scheduler`](V1/routes/forward_scheduler.py) | Topological greedy forward sweep. FEFO producer pick per ingredient (L19); atomic AND-join for Building lots (§4.2); L18 prefers Building primary `6001`; L11 flag-and-continue on infeasibility. |
| 10 | [`diagnostics`](V1/routes/diagnostics.py) | Recompute every consumer-producer gap; flag `[MIN, MAX]` breaches (inclusive bounds, L22); classify Building → Curing handoffs. |
| 11 | [`kpi`](V1/routes/kpi.py) | OTIF % at the Building → Curing handoff, aging-violation totals, processing minutes, schedule span, per-machine utilisation. |
| 12 | [`visualisation`](V1/routes/visualisation.py) | `bom_graph.svg`, `schedule.csv`, `machine_view.csv`, and `gantt_<block>.html` for three sample blocks. |

Module boundaries are typed frozen dataclasses (`AuditResult`, `NormalisedResult`, `BomGraph`, `DemandResult`, `LotsResult`, `LotDagResult`, `FeasibilityResult`, `DurationResult`, `ScheduleResult`, `DiagnosticsResult`, `KpiResult`). Each module can be invoked from a Python REPL given the upstream result, which makes incremental debugging straightforward.

---

## Configuration

All tunables live in [V1/config/pilot.yaml](V1/config/pilot.yaml). The file is loaded once at startup into a frozen [`Settings`](V1/config/settings.py) dataclass; downstream modules read from it. The schema:

```yaml
pilot:
  sku_code: "1325220516095HTMX0"
  green_tyre_code: "GT2056516TAXIMXTL"
  curing_press: "14811"            # string — leading zeros matter (L23)
  horizon_start: "2026-05-17 06:49"
  horizon_end:   "2026-05-30 22:19"
  total_demand_tyres: 2620

t0:
  auto: true                       # L17 — data-driven anchor (default)
  safety_buffer_min: 60            # extra minutes added between earliest-feasible-start and curing
  default: "2026-05-01 07:00"      # fallback when auto: false
  guardrail_assertion: true        # L17 — HALT if t0 + longest MIN-aging path > first curing start

# Auto-t0 (L17, implemented):
#   t0 = first_curing_start − critical_path − safety_buffer_min
#   where `critical_path` is the longest sum of (per-item duration + min_aging)
#   along any leaf → SKU walk through the BOM. Per-item duration is estimated
#   from routing using the same UOM rules as time_calculation, applied to
#   one curing block's worth of demand (64 tyres × per-tyre BOM walk).
#   Switching to `auto: false` uses the literal `default` instead.

efficiency:
  factor: 0.95                     # L10 / L20

defaults:
  transfer_time_min: 10            # §9 #3 fallback when routing transfer_time is null
  changeover_min_v1: 0             # L8 — V1 sets changeover to 0 always

building:
  pool: ["6001", "6002", "6003", "6004", "7001", "7002", "7003", "7004"]
  primary: "6001"                  # L18 — V1 deterministic primary; spill on aging-MAX breach

exclusions:
  capstrip_items: [...]            # L12 — five items hard-excluded from scheduling
work_away_items: [...]             # L13 — four items assumed already available
green_tyre_components: [...]       # 8-component AND-join set for Building

output:
  run_id_format: "%H%M-%d-%m-%Y"
  root: "output"
```

Adding a new tunable means (a) adding a YAML key, (b) adding a `Settings` field, (c) updating the loader, and (d) reading it at the usage point. There is no environment-variable shortcut — all configuration is declarative and reproducible.

---

## Determinism guarantees

Per CLAUDE.md L11 / §12.2 / §13:

- **No `random`.** No wall-clock-dependent defaults except the run-id timestamp, which is injectable for tests (see `tests/integration/test_end_to_end.py`).
- **Every sort is explicit** — `sorted(...)`, `kind="stable"` on every `DataFrame.sort_values`. No reliance on dict insertion order or hash randomisation.
- **Single `ceil` rounding direction** throughout the codebase, via [V1/utilities/time_math.py](V1/utilities/time_math.py). Duplicating `math.ceil(x / 60)` elsewhere is treated as a defect (L23).
- **Datetime ↔ minute conversion** lives at exactly two boundaries: the audit / unit-normalisation step (in) and the schedule writer (out). No `pd.Timestamp` arithmetic anywhere in the scheduler core.
- **`machine_id` is a string end-to-end** so leading zeros on the mixer pool (`0201`, `0202`, …) survive (L23).
- **`lot_id` is the canonical tiebreaker** for every dispatch and FEFO decision (L15 step 4, L19).

The integration test `test_deterministic_artefacts_byte_identical` runs the full pipeline twice and asserts the 9 deterministic output files are byte-identical between runs. This is the regression gate for non-deterministic changes.

---

## HALT exit codes

The engine exits with a stable non-zero code so CI / wrapper scripts can branch on the binding finding. Defined in [V1/config/halt_codes.py](V1/config/halt_codes.py).

| Code | Name | Meaning |
|---:|---|---|
| 0 | `OK` | All 12 routes ran; every artefact written. |
| 10 | `AUDIT_NULL_PROC_TIME` | A routing row has a null `proc_time` (§9 #4, §8.D). |
| 11 | `AUDIT_MISSING_AGING` | A mandatory pilot item is absent from the Aging Master (§9 #8). |
| 12 | `AUDIT_MISSING_ITEMTYPE` | A mandatory pilot item is absent from the ItemType Master (§9 #8). |
| 20 | `LOT_SIZING_TIGHT_AGING` | A single-block lot is below `MPQ_Min` and is aging-isolated from all other demand of the same item (§8.C). |
| 30 | `T0_GUARDRAIL_VIOLATION` | `t0 + sum(MIN_aging)` along the longest BOM path > `first_curing_start` (L17). |

In every HALT case the engine still writes `audit_report.md` and `routing_cleaned.csv` so the planner has the evidence in hand without re-running.

---

## Testing

```bash
uv run pytest tests -q                  # all 215 tests
uv run pytest tests/unit -q             # 209 unit tests
uv run pytest tests/integration -v      # 6 end-to-end + byte-identical re-run tests
```

### Five golden fixtures (CLAUDE.md §17)

Hand-computed cases that pin down the trickiest behaviours. Inputs are isolated under `tests/fixtures/<fixture>/inputs/`; unit tests under `tests/unit/` consume these.

| # | Fixture | What it locks in |
|---|---|---|
| 1 | `f1_eht1000_24h_squeeze` | Tightest aging window in the pilot: EHT1000 24-hour MAX into curing block #1. Inclusive boundary at exactly 1440 min (L22). |
| 2 | `f2_bd_fillering_halt` | Null `proc_time` on `BD-12843443-4` Fillering → HALT before any `schedule.csv` is written. |
| 3 | `f3_eht1000_duplicate_row` | Two routing rows for `EHT1000 -480MM/90°` calendering — `is_primary == 1.0` kept, NaN dropped, logged WARN (L7). |
| 4 | `f4_b460_mixed_unit` | `B460` aging has `MinAging = 4 Hours` and `MaxAging = 4 Days`. Normaliser must output `(240, 5760)` minutes. |
| 5 | `f5_mpq_tight_aging_halt` | Synthetic single-block demand < `MPQ_Min` with the next block beyond aging-MAX. HALT in `lot_sizing` (§8.C). |

### Integration tests

[tests/integration/test_end_to_end.py](tests/integration/test_end_to_end.py) covers two scenarios:

1. **HALT path** — vanilla pilot inputs. Asserts exit 10, `audit_report.md` + `routing_cleaned.csv` present, all downstream artefacts absent.
2. **Full path** — same inputs with `BD-12843443-4` Fillering `proc_time` set to 60 SEC/BATCH. Asserts every §11 artefact is written, no machine double-booking, OTIF % is reported and bounded `[0, 100]`, and **two consecutive runs produce byte-identical outputs** across the 9 deterministic files.

---

## Project layout

```
.
├── CLAUDE.md                 # Authoritative spec — read first
├── README.md                 # This file — how to install, run, and read outputs
├── pyproject.toml            # uv-managed deps; Python ≥ 3.11
├── input/                    # Raw inputs (read-only)
│   ├── BTP_PCR_May_Curing_Schedule.csv
│   ├── BTP_Routing_…BOM_Final (1).xlsx
│   └── JKT_BTP_Forward_Scheduler_Problem_Statement.pdf
├── output/<HHMM-DD-MM-YYYY>/ # One dated folder per run; never overwritten
├── V1/
│   ├── config/               # pilot.yaml + Settings + HaltCode + enums
│   ├── models/               # Frozen dataclasses (Lot, ScheduledLot, …)
│   ├── routes/               # 12 pipeline modules
│   ├── utilities/            # Pure helpers (time math, FEFO, BOM walker, machine parser, unit conversion)
│   ├── reports/              # Output writers — datetime ↔ minute boundary
│   └── setups/               # CLI, run context, bootstrap orchestrator
├── tests/
│   ├── conftest.py           # Shared fixtures
│   ├── fixtures/             # 5 golden cases from CLAUDE.md §17 (inputs + notes)
│   ├── unit/                 # 209 unit tests across every module + utility
│   └── integration/          # 6 end-to-end + byte-identical re-run tests
└── docs/
    └── methodology.md        # Approach, assumptions, acceptance evidence
```

---

## V1 scope and known simplifications

V1 prioritises **correctness over optimisation**. CLAUDE.md §1.5 enumerates what is intentionally out of V1 — changeover modelling (currently 0 min, L8), machine-utilisation optimisation, same-product clustering on shared resources, rescheduling / repair loops. Those land in V2.

The codebase additionally carries four implementation-level simplifications, **documented in the module docstrings** rather than hidden:

1. **Forward scheduler uses a topological greedy sweep**, not the strict event-driven dispatcher specified by L21. Sequential dispatch is deterministic on the pilot data; the formal event heap with `(event_minute, event_class, lot_id)` ordering, and the full L15 LSF tiebreak chain, are V2 work.
2. **Soft-reservation expiry / release (L16) is not modelled.** The reservation log emits `created` + `consumed` rows at commit; `expired` and `released` events do not occur because the topo-greedy dispatcher has no contention.
3. **Backward feasibility uses the min-aging chain only.** §15 step 15 wanted `effective_gap + processing_time` along the longest path; the V1 implementation drops the processing term, yielding a conservative (i.e. tighter) deadline. Any schedule that survives is feasible.
4. **§9 finding #9** (informal `predecessor_rule` text validation) is not implemented; `operation_seq` is the structured signal we honour.

These are not gaps in correctness — every hard constraint in CLAUDE.md §5 is enforced and self-reported. They are the concrete starting points for V2.

---

## References

- [CLAUDE.md](CLAUDE.md) — authoritative project brief: 23 locked decisions, 26-step approach flow, 5 golden fixtures, status log.
- [docs/methodology.md](docs/methodology.md) — methodology write-up: architecture, evidence, acceptance against the problem-statement criteria.
- [V1/config/pilot.yaml](V1/config/pilot.yaml) — single source of tunables.
- [V1/config/halt_codes.py](V1/config/halt_codes.py) — exit-code reference.
- [tests/integration/test_end_to_end.py](tests/integration/test_end_to_end.py) — HALT-path + full-path + byte-identical re-run tests.
- [.claude/agents/plant-scheduler-reviewer.md](.claude/agents/plant-scheduler-reviewer.md) — read-only domain-review agent for evaluating the scheduling approach against real plant operations.
- [.claude/agents/scheduler-code-reviewer.md](.claude/agents/scheduler-code-reviewer.md) — read-only code-review agent for auditing the implementation against CLAUDE.md.
