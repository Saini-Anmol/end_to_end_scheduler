# JK Tyre BTP — Forward Production Scheduler

This file is the persistent project brief for any Claude Code session working in this directory. Read it end-to-end before writing any code.

---

## 1. Project context

Build a **deterministic, BOM-driven forward production scheduler** for the JK Tyre Banmore Tyre Plant (BTP). The plant manufactures Passenger-Car Radial (PCR) tyres through a long chain of operations: Mixing → Final Mixing → Calendering → Cutting / Slitting → Ply Cutting → Bead Building → Extrusion → Tyre Building → Curing.

**Curing is the last operation and is a FIXED INPUT.** The engine must take the published May curing schedule as-is and produce a fully time-stamped, machine-assigned schedule for **every upstream operation** of one pilot SKU.

What this engine is NOT:
- NOT an optimiser that re-arranges curing.
- NOT a demand forecaster.
- NOT a labour / energy / cost model.

Only material flow, machine assignment, and time.

---

## 1.5 Version scope — V1 vs V2+

**V1 (current build) — goal: DEMAND FULFILMENT ONLY.**
Prove that every curing block in the May plan can be fed on time with all 8 components within their aging windows, using a deterministic forward pass. The KPIs we care about in V1 are:
- **OTIF %** at the Building → Curing handoff (per block).
- **Count of aging violations** (per edge).
- **Count of infeasibilities** (per lot, with binding constraint named).
- **Coverage** — every in-scope operation has a scheduled lot.

**V1 intentionally ignores:**
- **Changeover minutes** — treat changeover as **0 min** in V1, even between different products on the same machine. The `routed_product` change is logged but does not consume time. (L8 below records the V1 value and the V2 model.)
- **Machine utilisation as an optimisation target** — utilisation is reported in the KPI sheet for visibility, but the engine does not try to maximise it.
- **Tyre-building primary-machine clustering for changeover savings** — primary-machine pinning (L3) is for floor-discipline, not for changeover.
- **Rescheduling / repair loops** — when an aging window or AND-join cannot be satisfied, the engine flags and continues (L11). No backtracking, no curing shift.

**V2+ (later) — optimisation layer on top of V1.**
Adds changeover modelling (15 min different product / 0 same), utilisation as an optimisation objective, same-product clustering on shared machines (especially FRC and the mixers), and any KPIs the planning team prioritises after V1 lands. **Do not touch any V2 concern until V1 is correct and reproducible.**

---

## 2. Pilot SKU

| Attribute | Value |
|---|---|
| SKU code | `1325220516095HTMX0` |
| Description | 205/65 R16 Passenger-Car Radial (Taxi MX TL) |
| Green tyre code | `GT2056516TAXIMXTL` |
| Curing press | `14811` (single press for this SKU in the May plan) |
| Horizon | 2026-05-17 06:49 → 2026-05-30 22:19 |
| Curing rows | 42 (mostly 64 tyres / 8-hr block, 15-min cycle) |
| Total demand | 2,620 tyres |
| Pre-existing green-tyre inventory | 0 on every row |

The Green Tyre has **9 BOM children**, of which **8 are in scope** (the Capstrip chain is out of scope for this phase):

| # | Component code | Item type | In scope |
|---|---|---|---|
| 1 | `CPJ1218-162MM/29°` | Rubberized Steel Belt | Yes |
| 2 | `CPJ1218-154MM/29°-1` | Rubberized Steel Belt | Yes |
| 3 | `TRD2056516TAXIMXTL` | Tread | Yes |
| 4 | `IL2056516TAXIMXTL` | Inner Liner | Yes |
| 5 | `SSW2056516TAXIMXTL` | Sidewall | Yes |
| 6 | `EHT1000-640MM/90°` | Rubberized Ply | Yes |
| 7 | `EHT1000 -480MM/90°` | Rubberized Ply | Yes |
| 8 | `BD-12843443-4` | Bead Apex | Yes |
| — | `CAP 66 - CAPSTRIP` | Cap Strip | **OUT OF SCOPE** (BOM incomplete) |

The BOM is **7 levels deep** end-to-end (SKU → Green Tyre → component → sub-component → final compound → master compounds → raw).

---

## 3. Input files (do NOT modify)

All three live in the project root.

### 3.1 `BTP_PCR_May_Curing_Schedule.csv`
14,292 rows over the full May plan; **42 rows for the pilot SKU**.
Columns: `Date, Shift, Machine, SKUCode, StartTime, EndTime, Qty, CycleTime_min, GT_Inventory, Remarks, SKU_Description`.
Each pilot row is a non-negotiable demand event.

### 3.2 `BTP_Routing_1325216614081STMX0 BOM_Final (1).xlsx`
Six sheets:

| Sheet | Rows | Purpose |
|---|---|---|
| `BOM - 1325220516095HTMX0` | 65 | Parent → child consumption (qty + UOM) for the pilot SKU |
| `Routing - 1325220516095HTMX0` | 62 | Per produced item: op name, dept, eligible machines, proc_time + UOM, batch_size, transfer_time, is_primary, efficiency |
| `Aging Master` | 18,020 | ItemCode → MinAging / MaxAging with separate unit columns (Days / Hours / Minutes) |
| `Buffer Master` | 18 | ItemType → Buffer hours (NOT used — see Section 5) |
| `ItemType Master` | 19,134 | ItemCode → ItemType (drives MPQ lookup) |
| `MPQ` | 13 | ItemType → Min / Max run qty with UOM |

### 3.3 `JKT_BTP_Forward_Scheduler_Problem_Statement.pdf`
The authoritative problem definition. Section numbers cited throughout this file refer to it.

---

## 4. Departments, machines, and processing UOMs

| Department | Machines (eligible pool) | Notes |
|---|---|---|
| Mixing (Master) | `0201, 0202, 0203, 0204, 0205, 0206` (subset per item) | `proc_time` in SEC/BATCH with `batch_size` in KG |
| Final Mixing | `0201, 0202, 0203, 0204, 0205` (subset per item) | SEC/BATCH, batch_size KG |
| FOUR ROLL CALENDAR | `FRC` (single shared resource) | M/MIN or SEC/BATCH. **Bottleneck candidate** — calenders CPJ1218 (×2 cuts), EHT1000 (×2 cuts), and CAP 66 (out of scope) |
| Belt Cutter | `WBC, WBCNew` | M/MIN |
| FULL WIDTH SLITTER | `FWS, FWSNew` | M/MIN (Capstrip chain — out of scope) |
| Cap Strip Slitter | `CapStrip Slitter` | (out of scope) |
| Quintuplex Extruder | `Quintuplex` | M/MIN — Tread |
| TRC | `TRC` | M/MIN — Inner Liner |
| Duplex Extruder | `Duplex` | M/MIN — Sidewall |
| PLY CUTTER | `LTBC, HTBC, LTBCNew` | M/MIN |
| VIPO | `VIPO` | MIN with batch_size 100 NOS (beads) |
| AUTO AND MANUAL FILLERING | `FILLERING` | proc_time NULL — needs a default |
| Tyre Building (VMIMaxx GROUP) | `7001, 7002, 7003, 7004, 6001, 6002, 6003, 6004` (8 machines) | SEC per tyre — see plant policy |
| Curing | `14811` (fixed) | 750 SEC nominal cycle |

---

## 5. Hard constraints (Section 4 of the PDF)

Every constraint below MUST hold for every scheduled lot. Violations must be **detected and reported by the engine itself**, never silently fixed.

| # | Constraint | Rule |
|---|---|---|
| 4.1 | Aging window | For every BOM edge: consumer start time must satisfy `producer_end + MIN_aging ≤ consumer_start ≤ producer_end + MAX_aging`. Applies to **every edge including Building → Curing**. Both bounds are **inclusive** (see L22). |
| 4.2 | AND-join (BOM completeness) | Tyre Building consumes **8 mandatory components** — it cannot start until every one of them has at least one ready, in-window lot. Modelled as an **atomic hard reservation** of all 8 producer lots at the Building lot's start instant. |
| 4.3 | Machine eligibility | Every lot runs on a machine listed in the routing for that operation. One lot per machine at a time. |
| 4.4 | MPQ | Every lot satisfies `MPQ_Min`. Lots > `MPQ_Max` are split into equal sub-lots. |
| 4.5 | Curing is fixed | Curing rows are immovable. If aging or AND-join cannot be satisfied, **FLAG** the violation and continue — never shift curing. |
| 4.6 | Determinism | Same inputs → byte-identical outputs. No randomness, no wall-clock dependence. |

---

## 6. Soft rules (Section 5 of the PDF — plant policies)

- 24×7 operation. **No shift breaks or planned maintenance windows modelled in this phase.**
- **15-minute changeover** between different products on the same machine; 0 min for same product back-to-back. No changeover at machine cold-start. **V1 sets this to 0 min always** (see L8 / Section 1.5).
- **10-minute transfer** between a producer and its consumer, but interpreted via `effective_gap = MAX(transfer_time, MIN_aging)` per L14 — material can be in transit while it ages.
- **95% efficiency** on all machines: effective time = nominal_time / 0.95, rounded up to whole minutes (see L20).
- **Tyre Building**: commit to ONE Building machine for the pilot SKU and only spill to a 2nd/3rd if staying on the primary would force a component to age past its window.
- Null process times must be filled with a documented, justifiable default — **except `BD-12843443-4` Fillering, which HALTs the engine until the planner supplies a value** (Section 8.D).

---

## 7. Locked design decisions (confirmed with planner)

These decisions are settled. Do NOT revisit without explicit reversal from the user.

| # | Decision | Choice |
|---|---|---|
| L1 | **Demand grain** | **Per-block**, one Building lot per curing row. Each Building lot points to exactly one curing block for traceability. |
| L2 | **Starting inventory** | **Zero**. Engine produces every compound, ply, bead, etc. from raw. `t0` = the earliest mixer start that lets the longest BOM path reach the first curing block within aging-MAX. Pre-horizon raw materials are assumed bottomless. |
| L3 | **Building machine** | **Pin to one primary**. Engine selects the lowest-conflict machine from `7001-7004, 6001-6004` and assigns every pilot Building lot there. Spills to a 2nd/3rd machine ONLY when staying on the primary would cause an aging violation on any component. See L18 for the V1 placeholder. |
| L4 | **Aging vs Buffer Master** | **Aging Master is authoritative.** Buffer Master is ignored for this phase (treated as a legacy planning concept not in scope of the hard aging constraint). |
| L5 | **Aging clock anchor** | Timer starts at producer **END** time, stops at consumer **START** time. |
| L6 | **Master-to-master aging** | Full aging window applies on every BOM edge, including master-compound → master-compound (e.g., MB230 → MB231). |
| L7 | **Duplicate EHT1000 calendering row** | Use the row with `is_primary == 1.0`; ignore the `NaN` row. Log as data-quality finding. (Excel row 51 in the routing sheet.) |
| L8 | **Changeover** | **V1: 0 min always** (changeover is out of scope for the first build — see Section 1.5). V2 model (for later): 15 min whenever the previous lot's `routed_product` ≠ the next lot's `routed_product` on the same machine; 0 min for back-to-back same product. No changeover at machine cold-start. Added to processing time, not overlapped. |
| L9 | **Output time precision** | 1 minute (matches the curing CSV). |
| L10 | **Efficiency factor** | `effective_time = ceil(nominal_time / 0.95)` applied uniformly to every operation. Single ceil rounding direction throughout (see L20). |
| L11 | **Infeasibility behaviour** | **Flag and continue. No rescheduling engine, no repair loop, no backtracking.** Lots that cannot satisfy aging or AND-join are written to the infeasibility sheet with the binding constraint named, and the forward pass moves on. **Never shift curing.** |
| L12 | **Capstrip on ice** | **Skip everything related to the Capstrip chain entirely** (`CAP 66 - CAPSTRIP`, `CAP 66-MOTHERROLL`, `CAP 66`, `B616M`, `MB614`) per PDF Section 2.2. Confirmed incomplete in the supplied data: duplicate Aging Master rows with conflicting Max values, and no MPQ row for `Pre Cap Strip` item type. The planner will provide corrected data later; until then the engine MUST NOT attempt to schedule, lot-size, or even include these items in any output sheet. They may still appear in the BOM graph viz tagged "OUT OF SCOPE — awaiting data". |
| L13 | **"Work Away" entries** (`IL3 WA`, `JT444WA`, `HS106 WA`, `T4004WA`) | Treat as reclaim/scrap inputs, assumed already available. NOT scheduled as produced items. Log to data-quality findings. |
| L14 | **Transfer time + aging interplay** | `effective_gap = MAX(transfer_time, MIN_aging)`. Material can be in transit while it ages — the two waiting periods overlap on the wall clock, so the binding constraint is whichever is larger. Constraint: `producer_end + effective_gap ≤ consumer_start ≤ producer_end + MAX_aging`. Both bounds inclusive (L22). |
| L15 | **Dispatch tiebreak chain (LSF)** | When multiple lots are ready for the same machine at the same instant, apply in strict order: (1) **Least Slack First** — smallest `latest_acceptable_start − current_sim_time`; (2) **Earliest curing-block deadline** served by the lot; (3) **Longest downstream path remaining** (sum of MIN aging + processing minutes to Curing along the lot's heaviest descendant); (4) **`ItemCode` ascending alphabetical**. The chain is exhaustive — by step 4, ordering is deterministic. |
| L16 | **Soft reservation rule** | When a consumer lot identifies a producer via FEFO, it places a **soft reservation** on that producer lot. The reservation: (a) **expires** automatically at the consumer's `latest_acceptable_start` if the consumer has not yet started; (b) is **exclusive** — one consumer at a time holds the reservation on a producer lot; (c) is **invisible** to other FEFO scans while held (the reserved producer lot is not selectable by anyone else). State changes are logged (see Section 16). |
| L17 | **`t0` anchor (placeholder)** | Real L2-derived `t0` (earliest mixer start that lets the longest BOM path reach the first curing block within aging-MAX) is **DEFERRED**. For V1 prototyping use a single config parameter `t0`, default `2026-05-01 07:00`. **Guardrail assertion at run start** (L22-adjacent): `t0_minute + sum(MIN_aging) along longest BOM path ≤ first_curing_start_minute`. If the assertion fails, HALT and print the full path with its cumulative MIN aging. |
| L18 | **Building primary machine (V1 placeholder)** | V1 deterministic choice: lowest `machine_id` (lexicographic on string) from the eligible Building pool `{6001, 6002, 6003, 6004, 7001, 7002, 7003, 7004}` → **`6001`**. Spill rule from L3 still applies. The "lowest-conflict" optimisation deferred to V2. |
| L19 | **FEFO eligibility** | A producer lot is eligible for FEFO consumption by a consumer at `current_sim_time` only when `producer_end + MIN_aging ≤ current_sim_time`. Lots still inside their MIN aging window are not selectable, even if scheduled. Among eligible lots, FEFO picks the one whose `producer_end + MAX_aging` is soonest. Ties broken by `lot_id` ascending. |
| L20 | **Time domain** | All scheduling math happens in a single **integer-minute** domain. Conversion happens **once** in the audit step: `t0 → minute 0`; every wall-clock instant `inst → (inst − t0).total_seconds() // 60`. Conversion back to datetime happens **only** in the output writer. Unit-conversion table locked in audit: `SEC/BATCH → ceil(proc_time/60)`, `M/MIN → ceil(lot_qty_m / proc_time)`, `MIN → as-is`, Days/Hours/Minutes → minutes. `effective_min = ceil(nominal_min / 0.95)`. **Single `ceil` rounding direction throughout** — never round down, never round half-up. |
| L21 | **Event-driven dispatch** | The scheduler does NOT tick minute-by-minute. It maintains a min-heap of future events and jumps `current_sim_time` to the next event instant. **Event classes** (ordering at a tied integer minute): (1) **lot-completion** (a running lot reaches its end_minute), (2) **machine-free** (changeover/setup window ends — in V1 this is identical to lot-completion since changeover = 0), (3) **lot-aged-in** (a scheduled lot crosses `producer_end + MIN_aging` and becomes FEFO-eligible). Within a class, sort by `lot_id` ascending. LSF + L15 tiebreakers are re-applied at every event point. |
| L22 | **Aging-MAX boundary inclusive** | The aging-MAX comparison is `≤`, not `<`. Worked example: producer_end = 100, MAX = 1440 → consumer_start = 1540 is **compliant** (gap = 1440, equal to MAX); consumer_start = 1541 is a **violation** (gap = 1441). Same convention for MIN (`≥`) and for `effective_gap` (L14). Applies uniformly to every BOM edge, including Building → Curing. |
| L23 | **Data-shape locks** | (a) `lot_id` format = `{safe_item_code}__{op_seq}__{lot_seq:04d}` with `__` as separator. `safe_item_code` strips/transliterates spaces and `°` (e.g., `EHT1000 -480MM/90°` → `EHT1000_480MM_90deg`); the readable original is kept in a separate `item_code` column. (b) `machine_id` is **always a string** in every dataframe and every output sheet — leading zeros in `0201-0206` matter and must never be lost to int coercion. (c) Datetime ↔ minute boundary lives exclusively in audit (in) and output writer (out); no other module touches `pd.Timestamp`. (d) Unit-conversion table from L20 is the single source of truth — duplicate `ceil(x/60)` logic anywhere else is a defect. |

---

## 8. Standing assumptions (defaults — open to revision)

These are the working defaults for the four topics that still have nuance. Each must appear with its justification in the final methodology write-up.

| ID | Topic | Choice |
|---|---|---|
| C | **Compound lot sizing** | **Forward-aggregate** consecutive block demands into the largest lot that satisfies BOTH `lot_qty ≤ MPQ_Max` AND `lot_end + compound_aging_MAX ≥ latest_consumer_start` for every served block. Above `MPQ_Max`, split into **equal-sized** sub-lots (no remainder lot smaller than `MPQ_Min`). Record which curing blocks each lot serves in a `serves_blocks` list column. **HALT edge case (locked):** if a single block's demand is below `MPQ_Min` AND aggregation across blocks is blocked by aging-MAX, the engine **HALTs the run and reports the offending block + compound**. No silent over-production. Expected to be rare for this pilot. |
| D | **Null `proc_time` (`BD-12843443-4` Fillering)** | **Do NOT impute.** `proc_time` is the operation cycle time and is required input. The audit module HIGHLIGHTS every routing row with a missing `proc_time` and the engine refuses to schedule that operation until the planner supplies a value (via input edit or explicit config override). No silent defaults. |
| F | **Mixer pool size mismatch** (`alt_machine_count` is wrong on many rows) | **Ignore `alt_machine_count` entirely.** The audit step parses the messy `machines` cell (normalising quotes/encoding), produces a clean list, and **adds a derived column `eligible_machine_count`** to the cleaned routing artefact (`outputs/<date>/routing_cleaned.csv`). Original input file is not modified. Scheduler uses the derived count. |
| I | **Dispatch rule** | **Least Slack First**, with the full tiebreak chain locked in L15. **Inventory consumption** (matching a consumer lot to one of several committed producer lots): **FEFO**, with eligibility per L19 and reservation per L16. Deterministic. |

---

## 9. Data-quality findings to surface in the audit report

1. Aging Master rows where `MaxAgingUnit ≠ MinAgingUnit` (e.g., `B460`: 4 Days max / 4 Hours min). Normalise everything to minutes before any math. **Warn**, not HALT.
2. Machine cells use inconsistent quoting — mixed `'...'`, `"..."`, stray apostrophes. Parser must normalise into a clean list and surface a derived `eligible_machine_count`. **Warn**.
3. `transfer_time_min` is null on almost every routing row → fall back to plant default 10 min. **Warn** with default-used flag.
4. `BD-12843443-4` Fillering row has null `proc_time` → **HALT** the engine until the planner supplies a value (see Section 8.D — no silent defaults).
5. `EHT1000 -480MM/90°` calendering appears twice in the routing (Excel row 51 has `is_primary` NaN) — use the row with `is_primary == 1.0`. **Warn**.
6. `alt_machine_count` is wrong on many rows (says 8 mixers but only 5 listed) → ignore that column entirely; use the parsed machine list. **Warn**.
7. Capstrip chain has both **duplicate Aging Master rows with conflicting Max values** (e.g., `CAP 66 - CAPSTRIP`: 48 hr vs 24 hr vs 24 hr) AND **no MPQ row for the `Pre Cap Strip` item type** — these are the gaps that put Capstrip out of scope. **Warn** + auto-exclude (L12).
8. Pilot items missing from Aging Master / ItemType Master → **HALT** and ask planner (no silent defaults).
9. `predecessor_rule` text is informal English; the routing's `operation_seq` is the structured signal — use seq, validate against the rule text. **Warn** on mismatch.
10. `t0` guardrail (L17) failure → **HALT** with full longest-path printout.

**HALT vs Warn discipline:** HALT means the engine refuses to write `schedule.csv` and exits non-zero with the binding finding named. Warn means the engine continues and lists the finding in `audit_report.md`. The validation step splits findings into these two buckets explicitly.

---

## 10. Pipeline modules (each runnable in isolation)

The engine MUST be modular with inspectable intermediate outputs. Suggested structure:

1. **`audit`** — read raw files, normalise units to integer minutes (L20), log every data-quality finding to an audit report. Split findings into HALT vs Warn. Output: cleaned in-memory frames + `audit_report.md` + `routing_cleaned.csv`.
2. **`demand_explosion`** — walk the BOM from each curing row down to master compounds, computing per-edge demand quantities in the right UOMs. Output: a per-curing-block demand tree.
3. **`lot_sizing`** — apply MPQ and aging-MAX to convert per-demand quantities into viable production lots (Section 8.C, forward-aggregate). HALT on the tight-aging edge case. Output: list of lots with target qty, `serves_blocks`, and earliest/latest acceptable end-times.
4. **`graph_construction`** — build a directed graph of (lot → lot) edges with aging-min and aging-max attributes. Output: lot dependency graph for viz + scheduling.
5. **`backward_feasibility`** — produces feasibility limits ONLY (`latest_acceptable_start` scalar per lot). Does NOT commit any time. Pure forward pass owns all scheduling.
6. **`time_calculation`** — for each lot, compute nominal duration on each eligible machine (applying efficiency per L10/L20).
7. **`scheduling`** — **event-driven forward pass** (L21) respecting machine capacity, aging window, AND-join atomic reservation, FEFO eligibility (L19), soft reservation (L16), and LSF tiebreaks (L15). Output: lot-level schedule + reservation log.
8. **`diagnostics`** — aging-violations sheet, infeasibilities sheet, Building→Curing handoff classification (OK / LATE / EARLY).
9. **`kpi`** — total lots, OTIF %, changeover minutes (0 in V1), processing minutes, schedule span, per-machine utilisation.
10. **`viz`** — static BOM graph (HTML/PNG/SVG) + Gantt for 3 sample curing blocks (early / middle / late in horizon).

Each module reads from and writes to a **single dated outputs folder** (e.g., `outputs/2026-05-20/`).

---

## 11. Deliverables (Section 6 of the PDF)

| Artefact | Format |
|---|---|
| Lot-level schedule | One row per lot: `lot_id, item_code, item_type, machine_id, start_min, end_min, start_dt, end_dt, duration_min, qty, uom, serves_blocks, on_time_flag` |
| Machine-level view | Same lots sorted by `machine_id` + `start_min` |
| Building → Curing handoff report | One row per Building lot classified OK / LATE / EARLY with delta minutes |
| Aging-violations sheet | One row per breached consumer-predecessor pair: `consumer_lot, predecessor_lot, edge_min, edge_max, actual_gap, violation_type` |
| Infeasibilities sheet | One row per unschedulable lot with the binding constraint named |
| Reservation log | Per Section 16 — one row per soft-reservation state transition |
| KPI report | totals, OTIF %, utilisation, schedule span |
| BOM graph viz | static HTML/PNG/SVG, departments + precedence + aging windows |
| DAG export | machine-readable lot dependency graph (JSON or GraphML) for downstream tooling |
| Gantt | 3 sample blocks (early / middle / late) |
| Methodology write-up | 4–8 pages: approach, assumptions, limitations, close-call design choices |
| README | how to run the pipeline end-to-end from a fresh clone |

**Output-folder standard:** one dated folder per run (`outputs/<YYYY-MM-DD-HHMM>/`). Each run writes a fresh `audit_report.md`, `schedule.csv`, `machine_view.csv`, `building_to_curing.csv`, `aging_violations.csv`, `infeasibilities.csv`, `reservation_log.csv`, `kpi.csv`, `dag.json`, `bom_graph.svg`, `gantt_*.html`. No cross-run state, no append, no overwrite.

---

## 12. Acceptance criteria (Section 7 of the PDF — judged in this order)

1. **Correctness** — every hard constraint holds, violations are self-reported.
2. **Reproducibility** — re-running on same inputs is byte-identical.
3. **Explainability** — every lot points back to the raw-data row that defined its time, qty, and machine.
4. **Coverage** — every operation in the pilot BOM (ex-Capstrip) is scheduled.
5. **Diagnostics quality** — Building→Curing, aging violations, infeasibilities are complete and actionable.
6. **Code quality** — clean, modular, fresh-clone runnable with documented steps.
7. **Visualisation clarity** — graph and Gantt readable without a separate legend.

---

## 13. Coding conventions

- **Language**: Python recommended (per PDF). No specific framework requirement.
- **Determinism**: no `random`, no wall-clock-dependent defaults, sort every iteration order explicitly, fix any pandas operations that depend on dict-insertion order. Every heap pop must use a deterministic key (event class → lot_id, per L21).
- **Time math**: normalise everything to a single integer-minute domain at audit (L20); convert back to datetimes only in the output writer. No `Timestamp` arithmetic anywhere in `scheduling`.
- **Rounding**: single `ceil` direction (L20). Never round down, never round half-up.
- **No silent fallbacks**: every default value must be both (a) configured in one place and (b) logged when used.
- **Outputs**: written to `outputs/<YYYY-MM-DD-HHMM>/` so re-runs don't overwrite history.
- **One command to run end-to-end** from a fresh clone (e.g., `python -m scheduler.run --inputs . --outputs outputs/`).

---

## 14. Status

- **2026-05-20 (initial)** — Problem statement read, data audited at column level, 4 locked design decisions captured (L1–L4), 14 tentative assumptions documented (A–N).
- **2026-05-20 (updated)** — Planner ran through A–N. Confirmed and moved to locked: A→L5, B→L6, E→L7, G→L8, J→L9, K→L10, L→L11, M→L12, N→L13, H→L14. Four items kept as standing assumptions in Section 8 with revised wording: C (lot sizing, with edge-case flag), D (null proc_time → no silent imputation, HALT instead), F (ignore `alt_machine_count`, derive `eligible_machine_count`), I (Least Slack First + FEFO for inventory consumption).
- **2026-05-20 (Capstrip)** — Capstrip chain on ice. Skip in all modules until the planner supplies corrected data.
- **2026-05-20 (V1 scope)** — V1 build is scoped to **demand fulfilment only**. Changeover set to 0 min in V1; the 15/0 changeover model is deferred to V2. See new Section 1.5.
- **2026-05-20 (Round 1 review)** — Planner shared a 26-step proposed flow; reviewer flagged the **Rescheduling Engine (Critical — removed: forward pass flags and continues, no repair loop)**, **backward planner committing time (High — downgraded to feasibility-limits only, scalar `latest_acceptable_start`)**, **flat 15–20 min buffer (High — replaced by L14 `effective_gap`)**, **lot-sizing under-specification (High — forward-aggregate with explicit HALT, Section 8.C)**, **Building pinning absent (High — added L3/L18 enforcement in flow)**, **validation HALT/Warn split (High — Section 9 reorganised)**, plus Medium-severity items on FEFO eligibility, AND-join atomicity, determinism in dispatch, and Capstrip auto-exclusion. All accepted by the planner.
- **2026-05-20 (Round 2 review)** — Planner accepted Round 1 corrections; reviewer locked the LSF tiebreak chain (L15), soft reservation rule (L16), `t0` placeholder + guardrail (L17), MPQ + tight-aging HALT (Section 8.C), Building primary `6001` placeholder (L18), FEFO eligibility rule (L19), time conversion convention (L20), event-driven dispatch (L21), and the full output-artefact list (Section 11). Captured as L15–L21.
- **2026-05-20 (Round 3 review)** — Final pass. Reviewer locked **event ordering at tied integer minutes** (lot-completion → machine-free → lot-aged-in, then `lot_id` ascending, L21), **aging-MAX boundary inclusive** (`≤`, L22), **`t0` guardrail assertion at run start** (L17), **reservation log schema** (Section 16), **data-shape locks** for `lot_id`, `machine_id`, datetime ↔ minute boundary, and unit-conversion table (L23), and the **five golden test fixtures** to hand-compute on paper before any module is written (Section 17). Verdict: **GO. Coding can start.** Next step: scaffold the audit module and verify the five fixtures pass before touching the scheduler.

---

## 15. Approach flow (V1 — 26 steps)

This is the implementation spec. Numbered 1–26, gap-free. Every step is owned by a specific module from Section 10; every step has a deterministic, inspectable output.

1. **Load raw inputs.** Read `BTP_PCR_May_Curing_Schedule.csv`, all six sheets of `BTP_Routing_*.xlsx`, and the problem-statement PDF metadata. No mutation. (`audit`)

2. **Filter to pilot SKU.** Curing CSV → 42 rows where `SKUCode == '1325220516095HTMX0'`. Routing/BOM/Aging/ItemType/MPQ → subset to all items reachable from the pilot Green Tyre, **excluding the Capstrip chain (L12)**. (`audit`)

3. **Normalise units to integer minutes.** Apply L20 conversion table: `SEC/BATCH → ceil(/60)`, `M/MIN → ceil(lot_qty_m / proc_time)`, `MIN → as-is`, aging Days/Hours/Minutes → minutes. Materialise `proc_time_min`, `min_aging_min`, `max_aging_min`, `transfer_time_min` columns. (`audit`)

4. **Compute `t0` and minute-0 anchor.** Load `t0` from config (default `2026-05-01 07:00` per L17). Convert every wall-clock instant in the run to `(inst − t0) // 60`. **Run `t0` guardrail assertion** (L17): if `t0_minute + sum(MIN aging) along longest BOM path > first_curing_start_minute`, HALT and print the path. (`audit`)

5. **Parse messy machine cells.** Normalise quotes/encoding; produce a clean `machines` list per routing row; derive `eligible_machine_count` (Section 8.F). Store `machine_id` as **string** everywhere (L23). (`audit`)

6. **Classify data-quality findings.** Split into HALT and Warn buckets per Section 9. HALT cases stop the run before any scheduling math; Warn cases are listed in `audit_report.md` and the run continues. (`audit`)

7. **Handle EHT1000 duplicate.** Keep the routing row with `is_primary == 1.0`; drop the NaN row; log to Warn (L7, Section 9 finding #5). (`audit`)

8. **BOM explosion per curing block.** For each of the 42 pilot curing rows, walk the BOM downward and compute the per-edge demand quantity in the consumer's UOM. Result: a per-block demand tree, one row per (block, BOM-edge). (`demand_explosion`)

9. **Demand aggregation per item across blocks.** Group demand quantities by `item_code` while preserving the served-block list. This is the input to lot sizing. (`demand_explosion`)

10. **Lot sizing — forward aggregate.** For each item, build lots by walking served blocks in chronological order, accumulating qty into the current lot while both (a) `qty ≤ MPQ_Max` and (b) the aging-MAX horizon of the earliest served block still covers the latest. Close the lot and open a new one when either bound breaks. (`lot_sizing`, Section 8.C)

11. **Lot sizing — MPQ_Max split.** If a single block's demand exceeds `MPQ_Max`, split into equal sub-lots (no remainder lot smaller than `MPQ_Min`). (`lot_sizing`)

12. **Lot sizing — HALT on tight aging.** If a single block's demand < `MPQ_Min` AND aggregation is blocked by aging-MAX, HALT with the offending (block, compound) printed (Section 8.C). No silent over-production. (`lot_sizing`)

13. **Generate lot IDs.** `lot_id = {safe_item_code}__{op_seq}__{lot_seq:04d}` per L23. Store the readable `item_code` separately. (`lot_sizing`)

14. **Build the lot DAG.** One node per lot; one directed edge per BOM edge between served lots; attach `(min_aging_min, max_aging_min, effective_gap_min)` per L14. Export to `dag.json`. (`graph_construction`)

15. **Backward feasibility limits (NO time commit).** For each lot, compute `latest_acceptable_start_min` by walking backward from its served curing block(s), subtracting `effective_gap` and processing time along the longest path to Curing. **Produces a scalar per lot; does NOT assign a start time.** Forward pass owns all scheduling. (`backward_feasibility`)

16. **Per-lot processing duration on each eligible machine.** `duration_min = ceil(nominal_min / 0.95)` per L10/L20. Stored per (lot, machine) pair. (`time_calculation`)

17. **Initialise event-driven scheduler.** Set `current_sim_time = t0_minute`. Initialise empty machine-free heap (every machine free at `t0`), empty soft-reservation table, empty running-lots map. Seed the event heap with one synthetic "mixer cold-start" event at `t0` for every mixer in the eligible pool. (`scheduling`, L21)

18. **Event loop — pop next event.** Pop the heap by (event_minute, event_class_priority, `lot_id`). Event-class priority: lot-completion = 1, machine-free = 2, lot-aged-in = 3 (L21). Advance `current_sim_time` to the popped event's minute. (`scheduling`)

19. **Dispatch — build ready set.** At the current event, enumerate every lot whose (a) predecessors are all FEFO-eligible per L19, (b) `latest_acceptable_start_min ≥ current_sim_time` (else it's already infeasible, route to infeasibility sheet), and (c) has at least one free eligible machine. (`scheduling`)

20. **Dispatch — apply LSF tiebreak chain.** Sort the ready set by L15: (1) LSF, (2) earliest curing-block deadline served, (3) longest downstream path remaining, (4) `item_code` ascending. Pick the head. (`scheduling`)

21. **FEFO match + soft reservation.** For every BOM-predecessor of the picked lot, scan FEFO-eligible producer lots (L19), pick the one with the earliest `producer_end + MAX_aging`, place a **soft reservation** (L16). For Building lots, this is an **atomic AND-join hard reservation across all 8 components** — if any one of the 8 cannot reserve, release the others, route the Building lot to the infeasibility sheet with the missing component named, and continue (L11). (`scheduling`)

22. **Commit the lot.** Assign the chosen machine, set `start_min = current_sim_time`, `end_min = start_min + duration_min`. Push a `lot-completion` event at `end_min` and a `lot-aged-in` event at `end_min + min_aging_min`. Mark consumed soft reservations as `consumed` in the reservation log. (`scheduling`)

23. **Building primary-machine pinning.** For every Building lot, attempt to assign machine `6001` first (L18). Spill to `6002, 6003, ...` only if `6001` is busy at `current_sim_time` AND waiting on it would push any component past its aging-MAX (L3). (`scheduling`)

24. **Continue the loop.** Repeat steps 18–23 until the event heap is empty OR every curing block has a committed Building lot (or a logged infeasibility). Expired reservations are logged with `event_type = expired` per Section 16. (`scheduling`)

25. **Diagnostics & violations.** Walk the committed schedule, recompute every consumer-predecessor gap, flag any breach of `[MIN_aging, MAX_aging]` (inclusive bounds per L22) into `aging_violations.csv`. Classify every Building lot vs its curing block start as OK / LATE / EARLY. Compute OTIF %. (`diagnostics`, `kpi`)

26. **Write outputs.** All 11 artefacts from Section 11 into `outputs/<YYYY-MM-DD-HHMM>/`. Convert integer minutes back to datetimes ONLY here (L23). Render `bom_graph.svg` and `gantt_*.html` for the three sample blocks. Exit non-zero if any HALT condition fired earlier; otherwise exit 0 with a one-line summary printed to stdout. (`viz`, output writer)

---

## 16. Reservation log schema

One row per **state transition** on a soft reservation. Written at end-of-run to `reservation_log.csv` inside the dated outputs folder. **No cross-run persistence** — each run produces a fresh log.

| Column | Type | Description |
|---|---|---|
| `event_minute` | int | The integer minute at which the transition occurred (relative to `t0`). |
| `event_type` | enum | One of `created`, `consumed`, `expired`, `released`. |
| `consumer_lot_id` | string | The lot that placed (or held) the reservation. |
| `producer_lot_id` | string | The lot being reserved. |
| `item_code` | string | Producer item code (readable, with original spaces/`°` preserved). |
| `qty` | float | Reserved quantity in the producer's UOM. |
| `producer_end_min` | int | Producer's `end_min`. |
| `latest_acceptable_start_min` | int | Consumer's `latest_acceptable_start` — the auto-expiry instant. |

**Event-type semantics:**
- `created` — consumer FEFO-matched producer; reservation now exclusive (L16).
- `consumed` — consumer started, reservation converted to actual consumption.
- `expired` — `current_sim_time` reached `latest_acceptable_start_min` without consumer starting; reservation released automatically and producer becomes visible to other FEFO scans again.
- `released` — manual release (e.g., AND-join atomic rollback when one of 8 Building components cannot be reserved).

**Invariant:** every `created` row has exactly one matching downstream `consumed` OR `expired` OR `released` row. The diagnostics step asserts this at end-of-run.

---

## 17. Golden test fixtures

These **five fixtures must be hand-computed on paper and encoded as unit tests before any module is written**. They are the minimum acceptance bar for the audit + scheduling modules.

### Fixture 1 — EHT1000 24 h-MAX squeeze on curing block #1
- **Setup:** First pilot curing row, `2026-05-17 07:00`. EHT1000 has aging-MAX 24 h on its consumer edge.
- **Expected:** Scheduler places EHT1000 calendering lot such that `calender_end_min` falls within `[curing_start_min − 24h, curing_start_min − MIN_aging]` (inclusive both ends per L22). At least one such lot exists with no aging violation.
- **Passes iff:** the scheduled lot's gap to the Building-lot start is ≤ 1440 min and ≥ MIN_aging_min.

### Fixture 2 — `BD-12843443-4` Fillering HALT
- **Setup:** Routing row for `BD-12843443-4` Fillering operation has `proc_time = NaN`.
- **Expected:** Audit module classifies this as HALT (Section 9 finding #4). Engine exits non-zero **before** any `schedule.csv` is written. `audit_report.md` names the offending routing row.
- **Passes iff:** no `schedule.csv` exists in the output folder AND exit code ≠ 0 AND audit report contains the HALT line.

### Fixture 3 — EHT1000 duplicate routing row
- **Setup:** Routing sheet has two rows for `EHT1000 -480MM/90°` calendering: row 44 (`is_primary == 1.0`) and row 49 (`is_primary == NaN`).
- **Expected:** Audit keeps row 44, drops row 49, logs row 49 to Warn (not HALT). Scheduler uses row 44's machine list and processing time.
- **Passes iff:** `routing_cleaned.csv` contains exactly one row for that item × operation, and `audit_report.md` contains a Warn line citing row 49.

### Fixture 4 — `B460` mixed-unit aging
- **Setup:** Aging Master row for `B460` has `MinAging = 4` with unit `Hours` and `MaxAging = 4` with unit `Days`.
- **Expected:** Audit normaliser outputs `min_aging_min = 240`, `max_aging_min = 5760`. One Warn line cites the mixed-unit pair.
- **Passes iff:** the cleaned aging table shows `(240, 5760)` for `B460` AND the Warn line exists.

### Fixture 5 — MPQ + tight-aging HALT
- **Setup:** Construct a synthetic single-block demand for a compound where (a) `demand_qty < MPQ_Min` AND (b) the next block is more than `aging_MAX` minutes away — so aggregation is blocked.
- **Expected:** Lot-sizing module HALTs per Section 8.C with the offending (block, compound) printed. No `schedule.csv` written.
- **Passes iff:** exit code ≠ 0 AND the lot-sizing HALT line names both the block and the compound AND no schedule file is produced.

These five fixtures cover: (1) the tightest aging window in the pilot, (2) the only known proc_time HALT, (3) the documented duplicate-row data quirk, (4) the documented mixed-unit data quirk, (5) the only known lot-sizing impossibility mode. If all five pass, the audit and lot-sizing modules are trusted; the scheduler can then be wired in.
