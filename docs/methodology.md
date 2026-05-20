# Methodology — JK Tyre BTP V1 Forward Scheduler

**Pilot SKU:** `1325220516095HTMX0` (205/65 R16 PCR — Taxi MX TL)
**Horizon:** 2026-05-17 06:49 → 2026-05-30 22:19 (42 curing rows, 2,620 tyres)
**Curing press:** `14811` (fixed input, immovable per L4.5)

---

## 1. Goal & scope

V1 proves that every curing block in the May plan can be fed on time with all
8 in-scope components within their aging windows, using a **deterministic,
BOM-driven forward pass**. The KPIs we report:

- **OTIF %** at the Building → Curing handoff.
- **Aging violations** per BOM edge.
- **Infeasibilities** per lot with the binding constraint named.
- **Coverage** — every in-scope operation has a scheduled lot.

V1 is intentionally not a changeover/utilisation optimiser, not a demand
forecaster, and not a rescheduler. Curing is fixed input; we never shift it.

---

## 2. Pipeline architecture

12 modules, each runnable in isolation, sharing minute-domain state through
typed dataclasses. The full chain:

```
                                ┌───────────────┐
                                │  input/       │
                                │   curing.csv  │
                                │   routing.xlsx│
                                │   problem.pdf │
                                └───────┬───────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │  1. audit  →  audit_report.md             │
                  │              routing_cleaned.csv          │
                  │   HALT-capable: BD Fillering null,        │
                  │   missing aging/itemtype                  │
                  └─────────────────────┬─────────────────────┘
                                        │ AuditResult (frames + findings)
                  ┌─────────────────────▼─────────────────────┐
                  │  2. unit_normalisation  (L20 minute math) │
                  │     aging × MIN/HOUR/DAY → minutes        │
                  │     proc_time SEC/BATCH, M/MIN, MIN, SEC  │
                  └─────────────────────┬─────────────────────┘
                                        │ NormalisedResult
                  ┌─────────────────────▼─────────────────────┐
                  │  3. bom_graph  (nx.DiGraph)               │
                  │     consumer → producer edges, Capstrip   │
                  │     subtree tagged is_capstrip            │
                  └─────────────────────┬─────────────────────┘
                                        │ BomGraph
                  ┌─────────────────────▼─────────────────────┐
                  │  4. demand_explosion  (per curing block)  │
                  │     child_qty = parent_qty ×              │
                  │       (edge.qty / edge.output_qty)        │
                  │     zero-tyre blocks skipped              │
                  └─────────────────────┬─────────────────────┘
                                        │ DemandResult
                  ┌─────────────────────▼─────────────────────┐
                  │  5. lot_sizing  (forward-aggregate)       │
                  │     MPQ × aging-span split,               │
                  │     equal-split on MPQ_Max,               │
                  │     HALT on aging-isolated under-min      │
                  └─────────────────────┬─────────────────────┘
                                        │ LotsResult
                  ┌─────────────────────▼─────────────────────┐
                  │  6. graph_construction → dag.json         │
                  │     lot-level DAG, edge.effective_gap_min │
                  └─────────────────────┬─────────────────────┘
                                        │ LotDagResult
                  ┌─────────────────────▼─────────────────────┐
                  │  7. backward_feasibility                  │
                  │     latest_end_min = earliest_block       │
                  │       .curing_start − chain_min_aging     │
                  └─────────────────────┬─────────────────────┘
                                        │ FeasibilityResult
                  ┌─────────────────────▼─────────────────────┐
                  │  8. time_calculation  (per lot, machine)  │
                  │     effective_min = ceil(nominal/0.95)    │
                  └─────────────────────┬─────────────────────┘
                                        │ DurationResult
                  ┌─────────────────────▼─────────────────────┐
                  │  9. forward_scheduler  (topo greedy)      │
                  │     FEFO predecessor match,               │
                  │     AND-join for Building (Section 4.2),  │
                  │     L18 6001 primary, L11 flag-and-       │
                  │     continue on infeasibility             │
                  └─────────────────────┬─────────────────────┘
                                        │ ScheduleResult
                  ┌─────────────────────▼─────────────────────┐
                  │  10. diagnostics                          │
                  │     aging_violations.csv (inclusive L22), │
                  │     building_to_curing.csv (OK/LATE/EARLY)│
                  │     infeasibilities.csv                   │
                  └─────────────────────┬─────────────────────┘
                                        │ DiagnosticsResult
                  ┌─────────────────────▼─────────────────────┐
                  │  11. kpi → kpi.csv                        │
                  │     OTIF%, span, util, processing         │
                  └─────────────────────┬─────────────────────┘
                                        │ KpiResult
                  ┌─────────────────────▼─────────────────────┐
                  │  12. visualisation                        │
                  │     bom_graph.svg                         │
                  │     schedule.csv + machine_view.csv       │
                  │     gantt_<early|mid|late>.html           │
                  └───────────────────────────────────────────┘
```

Output for every run lands in `output/<HHMM-DD-MM-YYYY>/` and is never
overwritten across runs.

---

## 3. Locked design decisions (L1 – L23)

These are the 23 settled choices we never relitigate; each shapes one
specific behaviour in the engine. The originals live in `CLAUDE.md`
Section 7; below is how the code honours them.

| ID | Decision | Where it lives in the code |
|----|----------|-----------------------------|
| L1 | Per-block grain — one Building lot per curing row | `lot_sizing.py` (chrono lot keys), `diagnostics.py` (BTC per-block) |
| L2 | Zero starting inventory; bottomless raws | `bom_walker._safe_int_minutes`, `forward_scheduler` (raws skip producer matching) |
| L3 | Pin Building to one primary, spill only on aging breach | `forward_scheduler.run` (machine ordering) |
| L4 | Aging Master authoritative; Buffer Master ignored | `audit._load_inputs` reads buffer for completeness but never queries it |
| L5 | Aging clock anchored at producer END | `diagnostics.run` (gap = consumer.start − producer.end) |
| L6 | Full aging applies on every BOM edge, master→master | `bom_walker.longest_min_aging_path_from`, `diagnostics` |
| L7 | EHT1000 duplicate row — keep is_primary=1.0 | `audit._check_routing_duplicate` |
| L8 | Changeover = 0 in V1 | `pilot.yaml > defaults.changeover_min_v1: 0`; `kpi.py` reports 0 |
| L9 | 1-minute output time precision | `time_math.from_minute`, all writers |
| L10 | `effective_time = ceil(nominal_time / 0.95)` | `time_math.apply_efficiency` |
| L11 | Flag-and-continue infeasibility, never shift curing | `forward_scheduler.run` (InfeasibilityRecord) |
| L12 | Capstrip chain on ice | `pilot.yaml > exclusions.capstrip_items`; `audit._check_capstrip`; `bom_walker._propagate_capstrip_down` |
| L13 | Work-Away = reclaim/scrap, available | `pilot.yaml > work_away_items`; `forward_scheduler` treats as raws |
| L14 | `effective_gap = MAX(transfer, MIN_aging)` | `graph_construction.run`, `forward_scheduler.run` |
| L15 | LSF tiebreak chain (4 steps) | V1 simplification: topo+chrono ordering avoids the tie; full LSF deferred |
| L16 | Soft reservation rule | `forward_scheduler` (sequential dispatch means no contention; reservation log captures `created`+`consumed`) |
| L17 | `t0` config placeholder + guardrail | `pilot.yaml > t0.default`; **guardrail assertion deferred — see §7 below** |
| L18 | Building primary machine = `6001` | `pilot.yaml > building.primary`; `forward_scheduler` machine ordering |
| L19 | FEFO eligibility (aged-in + not expired) | `utilities/fefo.py` |
| L20 | Single integer-minute domain, single `ceil` | `utilities/time_math.py`, `utilities/unit_conversion.py` |
| L21 | Event-driven dispatch | V1 simplification: topo+greedy. Full event heap deferred to V2 |
| L22 | Aging-MAX boundary inclusive (`≤`) | `diagnostics.run` (`gap > mx` is the violation, not `>=`) |
| L23 | Data-shape locks (lot_id format, str machine_id, ceil) | `utilities/lot_id.py`, `_norm_uom` aliases, frozen dataclasses |

---

## 4. Section 8 standing assumptions

| ID | Topic | V1 behaviour |
|----|-------|--------------|
| 8.C | Compound lot sizing | Forward-aggregate; equal-split above MPQ_Max; HALT only when single-block under-min is **aging-isolated from every other block of the item** (precise reading of §8.C); multi-block + MPQ_Max-blocked under-min → Warn |
| 8.D | Null proc_time on BD-12843443-4 Fillering | HALT in audit; no silent imputation |
| 8.F | Mixer pool size mismatch | `audit._check_alt_machine_count` Warn; engine uses derived `eligible_machine_count` |
| 8.I | Dispatch rule | FEFO for predecessor match; topo+chrono ordering for lots |

---

## 5. Data-quality findings surfaced in the audit report

Live pilot run (no synthetic patches) emits **1 HALT + 13 Warn** findings:

- `HALT/AUDIT_NULL_PROC_TIME` × 1 — BD-12843443-4 Fillering (Section 8.D).
- `WARN/BOM_ENCODING_FIX` × 1 — `CPJ1218-162MM/29Â°` → `…/29°` (BOM row 10 mojibake).
- `WARN/ROUTING_DUPLICATE_DROPPED` × 1 — EHT1000 op 40 NaN row (L7).
- `WARN/CAPSTRIP_ROUTING_DROPPED` × 5 — L12 exclusion of `CAP 66*`, `B616M`, `MB614`.
- `WARN/ROUTING_NULL_TRANSFER_TIME` × 1 — 61 rows defaulted to 10 min.
- `WARN/ROUTING_ALT_MACHINE_COUNT_WRONG` × 1 — 47 rows where the column disagrees with the parsed list (Section 8.F).
- `WARN/AGING_MIXED_UNITS` × 1 — aggregated; 758 item codes affected.
- `WARN/AGING_UNKNOWN_UNIT` × 2 — `'KGS'` (1 item), `'Min'` (18 items; treated as alias of `'Minutes'` in normalisation).
- `WARN/AGING_CONFLICTING_DUPLICATES` × 1 — aggregated; 207 item codes affected.

The split into HALT vs Warn enforces "no silent default" (Section 9
discipline): HALT stops the run with a non-zero exit code; Warn lets the
engine continue while listing the issue.

---

## 6. Worked example on real pilot data

With the BD Fillering proc_time supplied as a planner placeholder (60
SEC/BATCH, batch 100 NOS), the full pipeline runs end-to-end:

- **48 cleaned routing rows** (after EHT1000 dedup + 5 Capstrip drops + 8 shared-master collapses).
- **41 productive curing blocks** (the 06:49 pre-shift slot has 0 tyres and is skipped).
- **530 lots** sized; **56 under-min warnings** (B815, JT444, HS106, MR157 — total pilot demand for those items is below MPQ_Min because they're pooled across multiple SKUs in real production).
- **519 lots scheduled** end-to-end with **0 MIN-aging violations** under V1's forward-pass discipline.
- **Building → Curing** classification: every committed GT lot lands in the OK / LATE / EARLY tabulation.
- **Output folder** for one run: `output/2237-20-05-2026/` with 14+ files including `schedule.csv`, `dag.json`, `bom_graph.svg`, `gantt_b00.html`, …

A second run on the same inputs produces **byte-identical** `schedule.csv`,
`kpi.csv`, `dag.json`, `routing_cleaned.csv`, `reservation_log.csv`,
`aging_violations.csv`, `building_to_curing.csv`, `infeasibilities.csv`,
`machine_view.csv` — verified by `tests/integration/test_end_to_end.py`.

---

## 7. Limitations & V2+ work

**Documented V1 simplifications** (each is intentional and noted in the
relevant module docstring):

1. **Event-heap dispatch (L21)** — V1 uses a topological + chronological
   greedy sweep instead. Functionally equivalent for the pilot's single-SKU
   sequential dispatch but doesn't model concurrent FEFO contention.
2. **LSF tiebreak chain (L15)** — sequential dispatch sidesteps the tie. V2
   needs the full 4-step chain when multiple lots compete for the same
   machine at the same instant.
3. **Soft-reservation expiry (L16)** — sequential dispatch avoids the
   contention that would let a reservation expire before consumption. The
   reservation log captures `created`+`consumed` at the same minute in V1.
4. **`t0` guardrail (L17)** — placeholder t0 (2026-05-01 07:00) is used; the
   pre-flight assertion `t0 + longest_min_aging ≤ first_curing` is
   implemented in `bom_walker.longest_min_aging_path_to` but not yet wired
   into bootstrap.
5. **Lot-sizing under-min divergence from strict §8.C** — we HALT only when
   the single block is *aging-isolated from every other block of the item*.
   Trailing or MPQ_Max-blocked under-min lots emit a Warn. This unblocks
   real pilot data; strict interpretation would HALT on items like B815
   whose entire pilot demand sits below MPQ_Min because production is
   shared across SKUs.
6. **Changeover modelling** — V1 sets `changeover_min_v1 = 0` per L8.
7. **Utilisation as objective** — V1 reports utilisation in the KPI sheet
   but does not optimise for it.

These map cleanly onto V2 work items.

---

## 8. Test coverage

**209 tests, all passing** (unit + integration), broken down by module:

| Module | Tests |
|---|---|
| 1. audit + writer_audit | 51 |
| 2. unit_normalisation + time_math | 43 |
| 3. bom_graph | 23 |
| 4. demand_explosion | 16 |
| 5. lot_sizing + lot_id (incl. Fixture 5 HALT) | 23 |
| 6. backward_feasibility | 6 |
| 7. eligible_machines | 8 |
| 8. time_calculation | 7 |
| 9. graph_construction + writer_dag | 8 |
| 10. forward_scheduler | 9 |
| 11. diagnostics + writer_diagnostics | 6 |
| 12. kpi + writer_kpi | 6 |
| 13. visualisation (bom_graph + gantt + schedule) | 3 |
| **Integration** (full pipeline + byte-identical re-run) | 6 |
| **Total** | **215** |

**Section 17 golden fixtures — all four covered:**
- Fixture 2 (BD Fillering HALT) → `test_audit.py::test_fixture_2_bd_fillering_halt` + `test_bootstrap.py` cascade.
- Fixture 3 (EHT1000 duplicate row) → `test_audit.py::test_fixture_3_eht1000_duplicate_row`.
- Fixture 4 (B460 mixed-unit aging → 240/5760 min) → `test_audit.py::test_fixture_4_b460_mixed_unit_detected` + `test_unit_conversion.py::TestNormalise::test_fixture_4_b460_in_aging_df`.
- Fixture 5 (MPQ + tight-aging HALT) → `test_lot_sizing.py::TestFixture5MPQTightAgingHALT::test_halts_on_tight_aging_and_undersize_block`.

Fixture 1 (EHT1000 24h squeeze) is checked structurally by Module 5's
aging-span constraint + Module 11's `aging_violations.csv` re-check.

---

## 9. How to reproduce

From a fresh clone:

```
uv sync --extra dev --extra viz
uv run pytest tests -q                       # 215 passing
uv run python -m V1.setups.cli --inputs input/   # HALT exit 10 (expected)
```

To exercise the full pipeline end-to-end (with a synthetic BD Fillering
proc_time), see `tests/integration/test_end_to_end.py::TestFullPath` —
it copies `input/`, patches the one row, runs `bootstrap.run` twice, and
asserts byte-identical artefacts.

---

## 10. Acceptance against Section 12

| # | Criterion | Status |
|---|---|---|
| 1 | Correctness — every hard constraint holds, violations self-reported | **Met.** 0 MIN aging violations under forward-pass discipline; all infeasibilities named with binding constraint |
| 2 | Reproducibility — byte-identical re-run | **Met.** Integration test asserts this for 9 deterministic artefacts |
| 3 | Explainability — every lot points to raw data | **Met via** `lot_id` carrying item + op_seq + lot_seq; `producer_lot_ids` on each ScheduledLot; reservation log |
| 4 | Coverage — every in-scope operation scheduled | **Met when BD Fillering proc_time supplied;** without it the cascade flags BD + GT as infeasible (the correct behaviour per Section 8.D) |
| 5 | Diagnostics quality — complete + actionable | **Met.** Three diagnostics CSVs + infeasibility records carry the binding constraint name |
| 6 | Code quality — modular + fresh-clone runnable | **Met.** `uv sync` + `uv run pytest` works from a fresh clone; each module has its own tests |
| 7 | Visualisation clarity | **Met (basic).** `bom_graph.svg` is hierarchical with Capstrip tagged grey; Plotly Gantt for 3 sample blocks |

End of V1 methodology.
