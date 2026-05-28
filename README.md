# JK Tyre BTP — Forward Production Scheduler

**Deterministic, BOM-driven forward production scheduler for the JK Tyre Banmore Tyre Plant (BTP) — Passenger-Car Radial pilot SKU `1325220516095HTMX0`.**

The engine takes a published curing schedule as a **fixed input** and produces a fully time-stamped, machine-assigned schedule for every upstream operation — Mixing, Final Mixing, Calendering, Cutting, Ply Cutting, Bead Building (incl. Capstrip), Extrusion, and Tyre Building. Curing is never moved; if upstream cannot feed it in time, the engine **flags the breach and continues** (never silently fixes demand).

This is the **V1 build**, scoped to **demand fulfilment only**. The KPIs that matter in V1 are OTIF % at the Building → Curing handoff, count of aging violations, count of infeasibilities, and coverage. Changeover modelling and utilisation optimisation are deferred to V2.

---

## Generate the schedule (one command)

```bash
uv sync --extra dev --extra viz          # one-time: install dependencies
uv run python main.py                     # generate the schedule → output/<HHMM-DD-MM-YYYY>/
```

Open the headline artefact: **`output/<latest>/btp_schedule.xlsx`** (start with the `summary`, `otif_by_block`, and `bottlenecks` sheets).

Run against a **different curing schedule** without touching code:

```bash
uv run python main.py --curing input/curing_schedule_30k_170presses_1day.xlsx
```

The `--curing` flag accepts an absolute path, a path relative to the working directory, or a bare filename inside `--inputs`; both `.csv` and `.xlsx` are supported.

> The authoritative project brief — all 23 locked design decisions (L1–L23), the 26-step approach flow, the 5 golden fixtures, and the standing assumptions — lives in [CLAUDE.md](CLAUDE.md). The methodology write-up lives in [docs/methodology.md](docs/methodology.md).

---

## Contents

- [Pilot SKU and horizon](#pilot-sku-and-horizon)
- [Quick start](#quick-start)
- [Inputs](#inputs)
- [Outputs](#outputs)
- [Reading the report — where to look first](#reading-the-report--where-to-look-first)
- [Pipeline architecture](#pipeline-architecture)
- [Scheduling logic — how lots get placed](#scheduling-logic--how-lots-get-placed)
- [Configuration](#configuration)
- [Data corrections applied to the input workbook](#data-corrections-applied-to-the-input-workbook)
- [Determinism guarantees](#determinism-guarantees)
- [HALT exit codes](#halt-exit-codes)
- [Testing](#testing)
- [Scenario testing harness](#scenario-testing-harness)
- [Project layout](#project-layout)
- [V1 scope and known simplifications](#v1-scope-and-known-simplifications)
- [References](#references)

---

## Pilot SKU and horizon

| Attribute | Value |
|---|---|
| SKU code | `1325220516095HTMX0` |
| Description | 205/65 R16 Passenger-Car Radial (Taxi MX TL) |
| Green tyre | `GT2056516TAXIMXTL` — **9 in-scope BOM children** (Capstrip now in scope — see [L12 reversal](#capstrip-now-in-scope-l12-reversed)) |
| Curing press | `14811` (fixed input, immovable per L4.5) |
| Default horizon | 2026-05-17 06:49 → 2026-05-30 22:19 (~14 days) |
| Curing blocks | 42 (mostly 64 tyres / 8-hr shift, 15-min press cycle) |
| Total demand | 2,620 tyres |
| Starting GT inventory | 0 on every row |
| BOM depth | 7 levels (SKU → Green Tyre → component → sub-component → final compound → master compound → raw) |

The horizon is determined by whichever curing schedule is loaded — the default May plan above, or any file passed via `--curing`.

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

The single canonical command:

```bash
uv run python main.py
```

`main.py` is a thin orchestrator at the project root: it puts the repo on `sys.path` and forwards to `V1.setups.cli.main`, defaulting `--inputs` to `./input/`. Equivalent invocations:

```bash
uv run python -m V1.setups.cli --inputs input/        # underlying module
uv run btp-scheduler --inputs input/                  # installed console script
```

### CLI flags

| Flag | Default | Purpose |
|---|---|---|
| `--inputs <dir>` | `./input/` | Folder holding the routing workbook + curing schedule. |
| `--outputs <dir>` | `./output/` (per `pilot.yaml`) | Output root; a fresh dated subfolder is created per run. |
| `--curing <path>` | `<inputs>/BTP_PCR_May_Curing_Schedule.csv` | Override the curing schedule file. Absolute, relative-to-cwd, or a bare filename. Accepts `.csv` or `.xlsx`. |

### Expected behaviour on the current inputs

The pipeline **runs end-to-end to completion** (exit 0) on the shipped inputs — every routing field the engine needs is now populated, so no HALT fires. The run writes the full workbook plus the diagram and Gantt artefacts. (The audit *will* HALT if a future data edit reintroduces a null `proc_time`, a missing Aging/ItemType row, or a t0 guardrail breach — see [HALT exit codes](#halt-exit-codes).)

---

## Inputs

Place the inputs in `input/`. The engine treats them as **read-only at runtime**; it never modifies the originals during a run.

| File | Purpose |
|---|---|
| `BTP_PCR_May_Curing_Schedule.csv` | The default curing schedule (the full May plan; 42 rows for the pilot SKU). Each pilot row is a non-negotiable demand event. Columns: `Date, Shift, Machine, SKUCode, StartTime, EndTime, Qty, CycleTime_min, GT_Inventory, Remarks, SKU_Description`. |
| `BTP_Routing_1325216614081STMX0 BOM_Final (1).xlsx` | Six sheets — `BOM - <sku>`, `Routing - <sku>`, `Aging Master` (the cleaned **7,180-row** dataset), `Buffer Master` (ignored per L4), `ItemType Master`, `MPQ` (**14 rows**). |
| `curing_schedule_30k_170presses_1day.xlsx` | Optional high-volume stress-test curing schedule (30,000 tyres, 170 presses, 1 day). Load via `--curing`. |
| `JKT_BTP_Forward_Scheduler_Problem_Statement.pdf` | Authoritative problem definition. Section numbers cited in `CLAUDE.md` resolve into this document. |

The audit module surfaces every data-quality finding it sees, classified as **HALT** or **WARN** per CLAUDE.md §9. WARN findings are logged and the pipeline continues; HALT findings stop the run before any schedule is written.

---

## Outputs

Every run creates a fresh dated folder `output/<HHMM-DD-MM-YYYY>/`. Folders are never overwritten across runs — re-running within the same minute raises `FileExistsError` (deliberate, so a prior run's artefacts are never lost).

A successful run emits **eight files**:

| Artefact | Content |
|---|---|
| **`btp_schedule.xlsx`** | **Headline planner artefact.** Single workbook with 14 sheets (see below). Every tabular output lives here. |
| `audit_report.md` | Markdown rendering of §9 findings, split into HALT vs WARN buckets with sheet / row citations. |
| `dag.json` | Machine-readable lot dependency graph — nodes + edges with aging windows and effective-gap minutes. |
| `bom_graph.svg` | Static BOM tree diagram. |
| `gantt_all.html` | Master Gantt: every machine × every lot, full horizon. Building machines pinned to the top. |
| `gantt_part1.html` · `gantt_part2.html` · `gantt_part3.html` | Three piece-wise Gantts splitting the schedule's time range into equal thirds, so dense early-horizon periods are legible. Each title carries its date range. |

Bars in every Gantt are coloured by `item_type`; hover surfaces `lot_id`, `item_code`, qty + uom, duration, `serves_blocks`, and `on_time_flag`. Machines are ordered by **process flow** (mixers at the bottom → Tyre Building at the top) so the final output is read first.

### Workbook sheet contents

The first four sheets are the **executive / diagnostic layer** — they answer "what happened and why" without scrolling raw data:

| Sheet | Columns / description |
|---|---|
| `summary` | **Sectioned executive summary** (`section, metric, value`), colour-banded by section: **RUN METADATA** · **LOT PRODUCTION FUNNEL** (lots made → scheduled → not-scheduled → on-time/late) · **GREEN TYRE SUPPLY** (blocks + tyres on-time vs late, OTIF %) · **BOTTLENECK** (busiest machine + the item hogging it) · **DATA QUALITY** (audit findings, aging violations). |
| `otif_by_block` | One row per curing block: `block_id, tyres, curing_start_min, gt_end_min, gap_min, classification, binding_component`. For every LATE block, `binding_component` names the latest-finishing component that delayed Building — the proximate cause. |
| `bottlenecks` | Machine utilisation ranked high→low: `machine_id, lots, busy_min, span_min, utilisation_pct, top_item, top_item_pct_of_machine`. The top rows are the binding resources for the schedule span. |
| `unscheduled` | Not-scheduled (infeasible) lots + the downstream curing blocks each would have fed: `lot_id, item_code, op_seq, binding_constraint, downstream_blocks_affected, n_blocks_affected, message`. Empty when every lot commits (the common case under L11 flag-and-continue). |

The remaining sheets are the **detail layer**:

| Sheet | Columns / description |
|---|---|
| `kpi` | Full KPI table: counts, OTIF %, aging-violation breakdown, processing minutes, schedule span, per-machine utilisation. |
| `schedule` | Lot-level schedule. `lot_id, item_code, item_type, op_seq, machine_id, start_min, end_min, duration_min, qty, uom, serves_blocks, on_time_flag, start_dt, end_dt`. `on_time_flag=False` marks lots that finished after their aging-MIN ceiling (L11). |
| `machine_view` | Same rows sorted by `(machine_id, start_min, lot_id)` for floor-level execution. |
| `building_to_curing` | One row per Building (GT) lot per served block. Classification = `OK` / `LATE` / `EARLY` / `ZERO_QTY`. |
| `aging_violations` | One row per breached consumer-producer pair: `consumer_lot, predecessor_lot, item_code, edge_min, edge_max, actual_gap, violation_type`. |
| `infeasibilities` | One row per unschedulable lot with the binding constraint named (`AND_JOIN`, `BLOCK_OVERLAP`, `AGING`, `MACHINE`, `DURATION`, `DEADLINE`). |
| `reservation_log` | Per CLAUDE.md §16: `event_minute, event_type, consumer_lot_id, producer_lot_id, item_code, qty, producer_end_min, latest_acceptable_start_min`. |
| `routing_cleaned` | Routing after dedup (L7) and machine-list normalisation (§8.F — adds derived `eligible_machine_count`). |
| `audit_halt` | HALT findings only. |
| `audit_warn` | WARN findings only. |

### HALT-run layout

A HALT run emits a slim workbook (`summary`, `audit_halt`, `audit_warn`, `routing_cleaned`) plus `audit_report.md`. No `dag.json`, `bom_graph.svg`, or Gantts — downstream routes never ran.

### Workbook formatting

Every sheet uses a three-row banner layout:

- **Row 1:** merged title bar (navy fill, bold white, 14 pt).
- **Row 2:** column headers (steel-blue fill, bold white).
- **Row 3+:** data, with freeze panes anchored at `A3` so the title and headers stay visible while scrolling.

Selected cells carry traffic-light conditional fills:

| Sheet | Column | Bands |
|---|---|---|
| `summary` | `section` | Rotating pastel bands per section (visual grouping). |
| `otif_by_block`, `building_to_curing` | `classification` | `OK` green · `LATE` light red · `EARLY` yellow · `ZERO_QTY` gray |
| `bottlenecks`, `kpi` | `utilisation_pct` / `*_util_pct` | ≥ 90 % green · 50–89.99 % yellow · < 50 % light red |
| `schedule`, `machine_view` | `on_time_flag` | `True` green · `False` light red |
| `aging_violations` | `violation_type` | Any breach → light red |
| `audit_halt`, `audit_warn` | `severity` | `HALT` light red · `WARN` yellow |

**Reading the workbook back programmatically:** the title row shifts the column header to Excel row 2. Use the helper to skip the offset:

```python
from V1.reports import writer_excel
schedule_df = writer_excel.read_sheet("output/<run>/btp_schedule.xlsx", "schedule")
```

This is equivalent to `pd.read_excel(path, sheet_name="schedule", header=1)`. All test suites and downstream tooling should prefer the helper so the layout offset is encapsulated.

---

## Reading the report — where to look first

1. **`summary`** → the headline funnel and OTIF in one screen. Read the `LOT PRODUCTION FUNNEL` (how many lots made vs scheduled vs late) and `GREEN TYRE SUPPLY` (blocks + tyres on-time vs late) sections.
2. **`otif_by_block`** → if OTIF is below target, this names *which* blocks are LATE and the *binding component* that delayed each.
3. **`bottlenecks`** → the systemic cause: the highest-utilisation machine and the item monopolising it.
4. **`unscheduled`** → only populated when a lot genuinely could not be placed; shows the downstream blocks it would have fed.

These four answer "did we meet demand, and if not, why" before you ever touch the lot-level `schedule` sheet.

---

## Pipeline architecture

Thirteen pipeline steps, each runnable in isolation. Orchestrated by [V1/setups/bootstrap.py](V1/setups/bootstrap.py). Steps 1–12 map to CLAUDE.md §10 / §15; step 13 is the bundled-workbook writer.

| # | Module | Purpose |
|---|---|---|
| 1 | [`audit`](V1/routes/audit.py) | Read raw inputs; surface data-quality findings; dedup masters; parse messy machine cells; fix `Â°` mojibake; warn on `SEC/BATCH` rows missing `batch_size` (`ROUTING_BATCH_UOM_NO_BATCH_SIZE`); drop the EHT1000 NaN-`is_primary` row (L7). HALT-capable. |
| 2a | [`t0_compute`](V1/setups/t0_compute.py) | L17 auto-`t0`: compute the longest BOM critical path (per-item duration + min-aging) from leaves to SKU, then anchor `t0 = first_curing_start − critical_path − safety_buffer_min`. Bypassed when `pilot.yaml`'s `t0.auto: false`. |
| 2b | [`unit_normalisation`](V1/utilities/unit_conversion.py) | Convert aging Days / Hours / Minutes (and `Hr/Hrs/Min` aliases) → integer minutes; convert routing `proc_time` SEC/BATCH, SEC, MIN → minutes via `ceil(x/60)`; anchor curing datetimes to the chosen `t0`. Single ceil rounding direction throughout (L20). |
| 3 | [`bom_graph`](V1/utilities/bom_walker.py) | Build an `nx.DiGraph` from the BOM; propagate `is_capstrip` down from the configured seeds (empty by default now — see L12 reversal); validate acyclicity. |
| 4 | [`demand_explosion`](V1/routes/demand_explosion.py) | Walk the BOM per curing block: `child_qty = parent_qty × (edge.qty / edge.output_qty)`. Aggregate per item; preserve `serves_blocks` chronologically. Zero-tyre blocks generate no demand. |
| 5 | [`lot_sizing`](V1/routes/lot_sizing.py) | Forward-aggregate consecutive block demands into the largest lot satisfying both `qty ≤ MPQ_Max` and the aging-MAX horizon. Equal-split when a single block exceeds `MPQ_Max`. **Green Tyre is special-cased to one lot per curing row (L1).** **HALT** when a single-block lot < `MPQ_Min` AND is aging-isolated from all other demand (§8.C). |
| 6 | [`graph_construction`](V1/routes/graph_construction.py) | Build the lot-level DAG; attach `effective_gap = MAX(transfer, MIN_aging)` per edge (L14). Emit `dag.json`. |
| 7 | [`backward_feasibility`](V1/routes/backward_feasibility.py) | Per-lot `latest_acceptable_end_min` from the min-aging chain to the SKU. Conservative — refined by the forward scheduler's CPM pass. |
| 8 | [`time_calculation`](V1/routes/time_calculation.py) | Per `(lot, eligible_machine)`: `duration_min = ceil(nominal_min / 0.95)` (L10 / L20). Three regimes: **continuous** (`M/MIN`, length-based), **per-batch** (when `batch_size` + `batch_UNIT` are set), and **per-cycle / per-unit** (Tyre Building consumes one cycle per `building_tyres_per_cycle` tyres; everything else is one cycle per output unit). |
| 9 | [`forward_scheduler`](V1/routes/forward_scheduler.py) | Topological greedy forward sweep with a **CPM backward pass**, **multi-producer FEFO**, atomic AND-join for Building lots (§4.2), L18 Building-primary preference, gap-aware machine intervals, and L11 flag-and-continue. See [Scheduling logic](#scheduling-logic--how-lots-get-placed). |
| 10 | [`diagnostics`](V1/routes/diagnostics.py) | Recompute every consumer-producer gap; flag `[MIN, MAX]` breaches (inclusive bounds, L22); classify Building → Curing handoffs as `OK` / `LATE` / `EARLY` / `ZERO_QTY`; mirror LATE / EARLY into aging violations with a synthetic `CURING__<block>` consumer id. |
| 11 | [`kpi`](V1/routes/kpi.py) | OTIF % at the Building → Curing handoff, aging-violation totals, processing minutes, schedule span, per-machine utilisation. |
| 12 | [`visualisation`](V1/routes/visualisation.py) | `bom_graph.svg` plus the master + three piece-wise Gantt HTMLs. The lot-level schedule + machine view live as sheets inside `btp_schedule.xlsx`. |
| 13 | [`writer_excel`](V1/reports/writer_excel.py) | Bundled `btp_schedule.xlsx` workbook (14 sheets) led by the sectioned `summary` + `otif_by_block` + `bottlenecks` + `unscheduled` analytical sheets. HALT runs get a slimmed-down workbook. |

Module boundaries are typed frozen dataclasses (`AuditResult`, `NormalisedResult`, `BomGraph`, `DemandResult`, `LotsResult`, `LotDagResult`, `FeasibilityResult`, `DurationResult`, `ScheduleResult`, `DiagnosticsResult`, `KpiResult`). Each module can be invoked from a Python REPL given the upstream result, which makes incremental debugging straightforward.

---

## Scheduling logic — how lots get placed

The forward scheduler ([V1/routes/forward_scheduler.py](V1/routes/forward_scheduler.py)) places lots children-first in topological order. Key behaviours:

- **CPM backward pass (`floor` / `ceiling`).** Before placement, each lot gets a `ceiling` (latest end honouring every consumer's aging-MIN) and a `floor` (earliest end). The `floor` uses **MIN across consumers** of `consumer_target_start − max_aging`: a single producer lot that serves both an early and a late block must end early enough to feed the *earliest* consumer. (Using MAX here would push the producer past the early consumer's window and silently lose those Building lots — that was a real bug, now fixed.)
- **Multi-producer FEFO.** When a consumer's per-block demand is split across several producer lots, the engine FEFO-matches each producer for exactly the per-block-intersection share (L19), so a single producer can feed several consumers across distinct blocks without over- or under-commitment.
- **Best-effort commit (L11 flag-and-continue).** When no producer is in-window at the consumer's earliest start, the engine commits anyway against the **least-expired** overlapping producer rather than dropping the lot. Diagnostics re-checks the gap and records the aging-MAX breach. This prevents one expired ingredient from cascading into dozens of phantom Building infeasibilities downstream — the schedule stays complete and the breaches are reported honestly.
- **AND-join for Building.** A Green-Tyre lot cannot start until **all 9 in-scope components** are reserved at the same instant (§4.2). If any one cannot reserve, the others are released and the GT lot routes to `infeasibilities`.
- **Building-machine pinning (L18).** Building prefers the configured primary `6001` and waits for it; it spills to another building machine only when staying on the primary would push the lot past its aging ceiling.

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
  safety_buffer_min: 60            # extra minutes between earliest-feasible-start and curing
  default: "2026-05-01 07:00"      # fallback when auto: false
  guardrail_assertion: true        # L17 — HALT if t0 + longest MIN-aging path > first curing start

efficiency:
  factor: 0.95                     # L10 / L20

defaults:
  transfer_time_min: 10            # §9 #3 fallback when routing transfer_time is null
  changeover_min_v1: 0             # L8 — V1 sets changeover to 0 always

building:
  pool: ["6001", "6002", "6003", "6004", "7001", "7002", "7003", "7004"]
  primary: "6001"                  # L18 — V1 deterministic primary; spill on aging breach
  tyres_per_cycle: 2               # VMIMaxx GROUP produces 2 green tyres per cycle

exclusions:
  capstrip_items: []               # L12 REVERSED — Capstrip now in scope (empty list)

work_away_items: [...]             # L13 — four reclaim/scrap items assumed always available
green_tyre_components: [...]       # 9-component AND-join set for Building (incl. CAP 66 - CAPSTRIP)

output:
  run_id_format: "%H%M-%d-%m-%Y"
  root: "output"
```

Adding a new tunable means (a) adding a YAML key, (b) adding a `Settings` field, (c) updating the loader, and (d) reading it at the usage point. There is no environment-variable shortcut — all configuration is declarative and reproducible.

### Capstrip now in scope (L12 reversed)

L12 originally put the Capstrip chain (`CAP 66 - CAPSTRIP`, `CAP 66-MOTHERROLL`, `CAP 66`, `B616M`, `MB614`) **on ice** because the supplied data had conflicting Aging Master rows (24h vs 48h for `CAP 66 - CAPSTRIP`) and missing MPQ rows. The latest aging dataset resolved the conflict, naming was standardised to `Capstrip`, and the `Pre Cap Strip` MPQ was supplied — so **L12 is reversed**: `exclusions.capstrip_items` is now empty and `CAP 66 - CAPSTRIP` is the **9th AND-join component** for Building.

Capstrip carries the tightest aging window (24h) and the deepest chain (5 levels), and `CAP 66` consumes the bulk of the single FRC calender (≈33 m of ply per tyre). Including it therefore makes the schedule materially harder and is the dominant driver of OTIF on the default May plan — see [`bottlenecks`](#workbook-sheet-contents). This is a genuine plant-capacity constraint (the single FRC), not a scheduler defect.

To take Capstrip back out of scope, re-populate `exclusions.capstrip_items` and remove `CAP 66 - CAPSTRIP` from `green_tyre_components`.

### Work-Away items (L13)

`IL3 WA`, `JT444WA`, `HS106 WA`, `T4004WA` are reclaim/scrap rubber. Per L13 they are treated as **always available** (bottomless inputs from `t0`) — the engine never schedules their production, never assigns them a machine, and never computes their timing.

---

## Data corrections applied to the input workbook

The shipped routing workbook reflects the following planner-confirmed corrections (each was a real data defect the audit either flagged or that surfaced during scheduling):

| Area | Correction |
|---|---|
| **Aging Master** | Replaced the noisy 18,020-row sheet with the cleaned **7,180-row** dataset. The old `B460` mixed-unit quirk (`4 Hours / 4 Days`) and the `HS106-FILLER 7X25` invalid `KGS` unit are gone. |
| **FILLERING (`BD-12843443-4`)** | Added `batch_size = 100`, `batch_UNIT = NOS`. Previously `proc_time_UOM = SEC/BATCH` had no batch size, so the engine priced it as 10 sec **per piece** (≈59 min/lot) instead of per 100-piece batch (≈2 min/lot) — wrongly making FILLERING look like the bottleneck. |
| **MPQ — Bead Bundle** | Renamed the `Bead` row to `Bead Bundle` so it matches the `BD-12843443-1` item-type (was silently un-constrained → one giant lot). |
| **MPQ — Bead / Bead Apex / Pre Cap Strip** | Supplied missing `Maximum Run Qty` (Bead Apex = 100 NOS; Pre Cap Strip = 50–214 MTR). |
| **MPQ — Tread** | Disambiguated UOM `MTR / Nos` → `MTR`. |
| **Capstrip naming** | Standardised ItemType `Cap Strip` → `Capstrip` so it matches the MPQ row. |

A new audit check — **`ROUTING_BATCH_UOM_NO_BATCH_SIZE`** — now warns whenever a `*/BATCH` proc-time UOM is missing its `batch_size`/`batch_UNIT`, so this class of mis-pricing is caught at audit time.

---

## Determinism guarantees

Per CLAUDE.md L11 / §12.2 / §13:

- **No `random`.** No wall-clock-dependent defaults except the run-id timestamp, which is injectable for tests.
- **Every sort is explicit** — `sorted(...)`, `kind="stable"` on every `DataFrame.sort_values`. No reliance on dict insertion order or hash randomisation.
- **Single `ceil` rounding direction** throughout, via [V1/utilities/time_math.py](V1/utilities/time_math.py). Duplicating `math.ceil(x / 60)` elsewhere is treated as a defect (L23).
- **Datetime ↔ minute conversion** lives at exactly two boundaries: the audit / unit-normalisation step (in) and the writers (out). No `pd.Timestamp` arithmetic anywhere in the scheduler core.
- **`machine_id` is a string end-to-end** so leading zeros on the mixer pool (`0201`, `0202`, …) survive (L23).
- **`lot_id` is the canonical tiebreaker** for every dispatch and FEFO decision (L15 step 4, L19).

The integration tests run the full pipeline twice and assert two complementary determinism guarantees:

- **`dag.json`** is **byte-identical** across runs (JSON serialisation with `sort_keys=True` is fully stable).
- **`btp_schedule.xlsx`** is **sheet-by-sheet dataframe-equal** across runs — the workbook bytes vary (openpyxl embeds a build timestamp) but every cell value is reproducible. The `summary` sheet is excluded because it carries the per-run `run_id` by design.

Together these are the regression gate for non-deterministic changes.

---

## HALT exit codes

The engine exits with a stable non-zero code so CI / wrapper scripts can branch on the binding finding. Defined in [V1/config/halt_codes.py](V1/config/halt_codes.py).

| Code | Name | Meaning |
|---:|---|---|
| 0 | `OK` | All routes ran; every artefact written. |
| 10 | `AUDIT_NULL_PROC_TIME` | A routing row has a null `proc_time` (§9 #4, §8.D). |
| 11 | `AUDIT_MISSING_AGING` | A mandatory pilot item is absent from the Aging Master (§9 #8). |
| 12 | `AUDIT_MISSING_ITEMTYPE` | A mandatory pilot item is absent from the ItemType Master (§9 #8). |
| 20 | `LOT_SIZING_TIGHT_AGING` | A single-block lot is below `MPQ_Min` and is aging-isolated from all other demand of the same item (§8.C). |
| 30 | `T0_GUARDRAIL_VIOLATION` | `t0 + sum(MIN_aging)` along the longest BOM path > `first_curing_start` (L17). |

In every HALT case the engine still writes `audit_report.md` and the slim workbook so the planner has the evidence in hand without re-running.

---

## Testing

```bash
uv run pytest tests -q                  # all 237 tests
uv run pytest tests/unit -q             # unit tests
uv run pytest tests/integration -v      # end-to-end + determinism tests
```

### Golden fixtures (CLAUDE.md §17)

Hand-computed cases that pin down the trickiest behaviours.

| # | Fixture | What it locks in |
|---|---|---|
| 1 | EHT1000 24 h squeeze | Tightest in-pilot aging window: EHT1000 24-hour MAX into curing block #1, inclusive boundary at exactly 1440 min (L22). |
| 2 | BD Fillering HALT | Null `proc_time` on `BD-12843443-4` Fillering → HALT before any schedule is written. |
| 3 | EHT1000 duplicate row | Two routing rows for `EHT1000 -480MM/90°` — `is_primary == 1.0` kept, NaN dropped, logged WARN (L7). |
| 4 | B460 mixed-unit aging | The mixed-unit detector + normaliser. The live data is now clean (B460 = `4 Hours / 96 Hours` → still `(240, 5760)` min); the detector is verified against a synthetic mixed-unit row so the logic stays covered regardless of live data. |
| 5 | MPQ + tight-aging HALT | Synthetic single-block demand < `MPQ_Min` with the next block beyond aging-MAX → HALT in `lot_sizing` (§8.C). |

### Integration tests

[tests/integration/test_end_to_end.py](tests/integration/test_end_to_end.py) runs the full chain and asserts every artefact is written, no machine double-booking, OTIF % bounded `[0, 100]`, and **two consecutive runs produce byte-identical / dataframe-equal outputs**.

---

## Scenario testing harness

Isolated scenario tests live under `testing/` and are **not** wired into the production pipeline or the test suite. They monkey-patch only inside their own process and write to a dedicated `output_testing/` root so they never collide with production runs.

| Script | Scenario | Run |
|---|---|---|
| [testing/run_30k_39_building.py](testing/run_30k_39_building.py) | 30,000-tyre demand assuming **39 Tyre-Building machines** available (vs the production fleet of 8). Answers "how long does the chain take to feed 30k GT through 39 parallel building lines, and what becomes the next bottleneck?" | `uv run python testing/run_30k_39_building.py` |

The harness overrides the GT routing's machine list to 39 machines, disables L18 single-primary pinning so all 39 are equally eligible, loads the 30k curing schedule, and writes a full workbook under `output_testing/30k_39bm/<run>/`. It restores every patched global in a `try/finally` block — `V1/` is never mutated.

---

## Project layout

```
.
├── CLAUDE.md                 # Authoritative spec — read first
├── README.md                 # This file — how to install, run, and read outputs
├── main.py                   # Canonical entry — `uv run python main.py`
├── pyproject.toml            # uv-managed deps; Python ≥ 3.11
├── input/                    # Raw inputs (read-only at runtime)
│   ├── BTP_PCR_May_Curing_Schedule.csv
│   ├── BTP_Routing_…BOM_Final (1).xlsx     # routing + BOM + 7,180-row Aging + MPQ
│   ├── curing_schedule_30k_170presses_1day.xlsx   # optional stress-test schedule
│   └── JKT_BTP_Forward_Scheduler_Problem_Statement.pdf
├── output/<HHMM-DD-MM-YYYY>/  # One dated folder per run; never overwritten
│                              # (btp_schedule.xlsx + audit_report.md + dag.json
│                              #  + bom_graph.svg + 4 Gantt HTMLs)
├── output_testing/           # Scenario-harness outputs (kept separate)
├── V1/
│   ├── config/               # pilot.yaml + Settings + HaltCode + enums
│   ├── models/               # Frozen dataclasses (Lot, ScheduledLot, …)
│   ├── routes/               # Pipeline modules — audit, demand_explosion,
│   │                         # lot_sizing, graph_construction,
│   │                         # backward_feasibility, time_calculation,
│   │                         # forward_scheduler, diagnostics, kpi,
│   │                         # visualisation
│   ├── utilities/            # Pure helpers — time math, FEFO, BOM walker,
│   │                         # machine parser, unit conversion, lot_id
│   ├── reports/              # Output writers (writer_audit, _diagnostics,
│   │                         #  _kpi, _schedule, _dag, _gantt, _bom_graph,
│   │                         #  _reservation_log, _excel)
│   └── setups/               # CLI, run context, bootstrap orchestrator,
│                             # t0_compute (L17 auto-anchor)
├── testing/                  # Isolated scenario harnesses (run_30k_39_building.py)
├── tests/
│   ├── conftest.py           # Shared fixtures
│   ├── fixtures/             # Golden cases from CLAUDE.md §17
│   ├── unit/                 # Unit tests across every module + utility
│   └── integration/          # End-to-end + byte-identical re-run tests
└── docs/
    └── methodology.md        # Approach, assumptions, acceptance evidence
```

---

## V1 scope and known simplifications

V1 prioritises **correctness over optimisation**. CLAUDE.md §1.5 enumerates what is intentionally out of V1 — changeover modelling (currently 0 min, L8), machine-utilisation optimisation, same-product clustering on shared resources, rescheduling / repair loops. Those land in V2.

The codebase additionally carries these implementation-level simplifications, **documented in the module docstrings** rather than hidden:

1. **Forward scheduler uses a topological greedy sweep**, not the strict event-driven dispatcher specified by L21. It carries a CPM backward pass (per-lot `floor` + `ceiling`) and gap-aware machine intervals to back-fill earlier free slots; the formal event heap and the full L15 LSF tiebreak chain are V2 work.
2. **Soft-reservation expiry / release (L16) is not separately modelled.** The reservation log emits `created` + `consumed` rows at commit.
3. **Backward feasibility uses the min-aging chain only.** The forward scheduler refines this with its own CPM pass using actual lot durations.
4. **§9 finding #9** (informal `predecessor_rule` text validation) is not implemented; `operation_seq` is the structured signal honoured.

These are not gaps in correctness — every hard constraint in CLAUDE.md §5 is enforced and self-reported. They are the concrete starting points for V2.

The dominant open item surfaced by V1 is **FRC calender capacity**: with Capstrip in scope, the single Four-Roll Calender is the binding resource. Lifting OTIF on high-volume schedules is a capacity decision (a second FRC or a dedicated capstrip line), not a code change.

---

## References

- [CLAUDE.md](CLAUDE.md) — authoritative project brief: 23 locked decisions, 26-step approach flow, 5 golden fixtures, status log.
- [docs/methodology.md](docs/methodology.md) — methodology write-up: architecture, evidence, acceptance against the problem-statement criteria.
- [V1/config/pilot.yaml](V1/config/pilot.yaml) — single source of tunables.
- [V1/config/halt_codes.py](V1/config/halt_codes.py) — exit-code reference.
- [testing/run_30k_39_building.py](testing/run_30k_39_building.py) — high-volume scenario harness.
- [tests/integration/test_end_to_end.py](tests/integration/test_end_to_end.py) — HALT-path + full-path + byte-identical re-run tests.
