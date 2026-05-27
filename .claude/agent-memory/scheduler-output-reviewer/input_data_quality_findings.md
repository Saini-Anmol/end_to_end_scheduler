---
name: input-data-quality-findings
description: Comprehensive audit of raw input files for JK Tyre BTP V1; 18 defects catalogued across BOM, Routing, Aging Master, Curing CSV; done 2026-05-22
metadata:
  type: project
---

## Input Data Quality Audit (2026-05-22)

### Critical Data Defects

**D1 — CPJ1218-162MM/29° BOM mojibake (CRITICAL)**
BOM Output column row 10 stores 'CPJ1218-162MM/29Â°' (Windows-1252 garbled UTF-8). The engine normalises this at audit (WARN/BOM_ENCODING_FIX) but the item appears as MISSING_ROUTING and MISSING_AGING/MISSING_ITYPE under its garbled form. Engine handles via decode, so downstream impact is minor if normalisation fires before lookup. Source: `BOM - 1325220516095HTMX0` row 10.

**D2 — BD-12843443-4 Fillering: batch_size IS null, proc_time is NOT null (High)**
CLAUDE.md Section 9 #4 says HALT on null proc_time. Actual: proc_time=10 SEC/BATCH, batch_size=NaN. So HALT should not fire per spec, and doesn't (0 HALTs in run 2327). But null batch_size means the scheduler cannot compute how many batches cover a given bead apex demand. This is an undocumented HALT-worthy gap. Routing sheet row 59.

**D3 — 8 exact-duplicate routing rows (Medium) — NOT just EHT1000**
9 (routed_product, operation_seq) pairs appear twice with byte-identical configs: B350, B460, CPJ1218, EHT1000 (this one has 1 NaN is_primary), MB1232, MB230, MB231, MB349, XMB349. CLAUDE.md L7 documents only the EHT1000 pair; the other 8 are unlogged duplicates. Engine silently picks first row per dedup logic; WARN only fires for EHT1000.

**D4 — MB230 machine cell missing leading apostrophe (Medium)**
Machine cell for MB230 is `0201'',''0202'',''0204'',''0205'',''0206''` (no leading `'`), while MB231 and others have `'0201'',''0202'',''...`. Parser must handle this inconsistency; if it fails, MB230 would get a wrong machine list. Audit catches this via ROUTING_ALT_MACHINE_COUNT_WRONG.

**D5 — Tread MPQ UOM ambiguous: "MTR / Nos" (Medium)**
MPQ row for Tread has UOM `MTR / Nos`. Scheduler must pick one interpretation. BOM says MM, routing says M/MIN. Correct unit for lot sizing is MTR. The `/ Nos` is a data entry artifact that the engine must strip.

**D6 — HS106-FILLER 7X25 aging MaxAgingUnit = 'KGS' (Medium)**
Aging Master row 237: MaxAging=72 with unit KGS. This is meaningless as an aging duration. Item does NOT appear in BOM (neither as output nor input) — it is a sub-ingredient of HS106 at the raw material level. Since HS106-FILLER 7X25 has no routing row and no BOM role in the pilot, the engine logs AGING_UNKNOWN_UNIT warn but doesn't schedule it. Correct unit is almost certainly Hours (72 Hours, matching other fillers). Planner should fix in Aging Master regardless.

**D7 — CPJ1218-154MM/29°-1 infeasibility is scheduling logic, NOT data (Low for planner)**
Infeasible block b16 (earliest_start=7718): CPJ1218-154MM/29°-1 has 24h max aging. If the FRC is shared and schedules CPJ1218 calendering too early for block 16, there's no data fix. The Aging Master data (0h min, 24h max) is correct and consistent with the published window.

**D8 — SSW infeasibility blocks b23/b30 are scheduling logic, NOT data (Low for planner)**
SSW max aging = 72h = 4320 min. Blocks b23 and b30 fall >4320 min after the nearest prior SSW lot's end. The engine needs to schedule a fresh SSW lot closer in time. The Aging Master value (72h) appears reasonable for sidewall compound. No data fix needed.

### Structural Data Gaps

**D9 — 1325220516095HTMX0 (the finished SKU) missing from Aging Master and ItemType Master**
Per cross-sheet check. This is the top-level finished tyre — it has no BOM parent and doesn't need aging metadata since curing is fixed. Low operational impact but technically incomplete.

**D10 — HS106-FILLER 7X25 appears only in Aging Master, not in BOM**
This item has no role in the pilot BOM graph. Its KGS aging unit is a data error in Aging Master. No scheduler impact since it's never consumed or produced in the pilot flow.

**D11 — 207 ItemCodes with conflicting Aging Master rows (WARN)**
Scheduler uses "first row wins" deduplication. For pilot items all duplicates have identical values (safe). For future SKUs this is a data governance risk.

**D12 — 47 rows where alt_machine_count != parsed machine count (WARN)**
VMIMaxx GROUP says alt_machine_count=7 but actual machines parsed=8 (machines 6001-6004, 7001-7004). This is the most impactful mismatch: if the engine used alt_machine_count it would undercount eligible Building machines. Engine correctly ignores this column per Section 8.F.

**D13 — Bead and Bead Apex MPQ has null Maximum Run Qty (Medium)**
MPQ rows for 'Bead' and 'Bead Apex' have no Max. Scheduler cannot split lots by max; it would need to treat these as unbounded. BD-12843443-1 (Bead Apex) has item type 'Bead Apex' — this gap could cause extremely large lots.

### Known Patterns (for future runs)
- All 9 duplicate routing pairs are byte-identical — safe to dedup by keeping first
- MB230 machine cell drops the leading apostrophe; MB231 has it; the parser normalises both correctly
- 'Min' (lowercase) as MinAgingUnit appears on 40 rows — normalised to Minutes by auditor
- Tread BOM qty in MM, routing in M/MIN: conversion factor = /1000 (mm to m). Engine must apply this.
- BOM consumption for belts/plies is in MM per tyre. For M/MIN duration: lot_qty_mm / 1000 / proc_time_mpm = minutes.

**Why:** Documented for future runs to avoid re-investigating the same known defects.
**How to apply:** In next run, if building duration is still wrong, check BD-12843443-4 batch_size handling. If SSW infeasible, don't look at Aging Master — look at scheduling sequencing.
