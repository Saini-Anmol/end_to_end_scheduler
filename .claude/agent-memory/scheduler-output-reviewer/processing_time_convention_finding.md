---
name: processing-time-convention-finding
description: Analysis of the per-lot vs per-2-tyres convention for VMIMaxx Tyre Building; engine uses cycle_size=2 (pilot.yaml) contradicting CLAUDE.md sec-per-tyre spec
metadata:
  type: project
---

## Processing Time Convention — Engine vs Spec Conflict

**Finding confirmed 2026-05-22 against run 2327-21-05-2026.**

### VMIMaxx Tyre Building (GT2056516TAXIMXTL, op_seq=70)
- Raw routing: `proc_time=60, proc_time_UOM=SEC, batch_size=NaN, batch_UNIT=NaN`
- CLAUDE.md §4 table says: "SEC per tyre -- see plant policy"
- pilot.yaml line 42 says: `tyres_per_cycle: 2  # Each VMIMaxx cycle produces 2 green tyres`
- Engine code (time_calculation.py, Regime C): uses `cycle_size = settings.building_tyres_per_cycle = 2`
- Engine result for qty=64 NOS: `n_cycles=32, per_cycle=1 min, nominal=32, eff=34 min` -- OBSERVED
- CLAUDE.md-correct result (60 SEC/tyre): `n_cycles=64, per_cycle=1 min, nominal=64, eff=68 min`
- **BUG: engine calculates 34 min for 64 tyres (30 SEC/tyre), spec says 60 SEC/tyre = 68 min**
- Industry benchmark: VMIMaxx PCR builds 1 tyre in 55–75 SEC. 60 SEC/tyre is realistic. 30 SEC/tyre is NOT plausible.
- Root cause: `pilot.yaml tyres_per_cycle: 2` introduced without matching update to CLAUDE.md. Comment says "Each VMIMaxx cycle produces 2 green tyres" -- this is not documented or confirmed in the problem statement.

### Mixing Operations (Regime B — correct)
- `proc_time=SEC/BATCH, batch_size=KG` → `n_batches=ceil(qty_kg/batch_size), per_batch=ceil(proc/60)` → matches observed.
- MB163: qty=411.52 KG, batch=210 KG, proc=216 SEC → n_batches=2, per_batch=4, nom=8, eff=9 ✓

### All M/MIN Operations (Regime A — correct)
- `ceil(qty_MTR / proc_rate_MMIN)` then `ceil(nominal/0.95)` — single ceil on net result ✓
- CPJ1218 FRC: qty=243840 MM, rate=20 → nom=13, eff=14 ✓
- Belt Cutter CPJ1218-162MM: qty=357120 MM, rate=20 → nom=18, eff=19 ✓
- EHT Ply Cutter 640MM: qty=239040 MM, rate=22 → nom=11, eff=12 ✓
- TRD Quintuplex: qty=63200 MM, rate=22 → nom=3, eff=4 ✓
- IL TRC: qty=156160 MM, rate=22 → nom=8, eff=9 ✓
- SSW Duplex: qty=53760 MM, rate=22 → nom=3, eff=4 ✓

### FRC SEC/BATCH with batch_size in M (Regime B — correct)
- EHT1000 FRC: proc=600 SEC/BATCH, batch=400 M (MTR); qty=163840 MM = 163.84 MTR
- n_batches=ceil(163.84/400)=1, per_batch=ceil(600/60)=10, nom=10, eff=11 ✓

### VIPO BD-12843443-1 (Regime B — correct)
- proc=10 MIN, batch_size=100 NOS; qty≈604800 MM, bom_output_qty=1350 MM/NOS (from BOM sheet)
- Observed duration=53 min; back-calc: nom=50, eff=ceil(50/0.95)=53 ✓ (n_batches=5)

### BD-12843443-4 Fillering note
- CLAUDE.md §8.D says HALT if proc_time null. Actual routing has proc_time=10 SEC/BATCH (not null).
- The HALT fixture in CLAUDE.md §17 may be based on an earlier version of the data where proc_time was NaN.
- As of run 2327-21-05-2026, Fillering is scheduled (duration=472 min) and NOT a HALT item.

### Fix Required
- Either: change `pilot.yaml tyres_per_cycle: 1` (so 60 SEC = 1 tyre, duration=68 min for 64 tyres)
- Or: confirm with planner that VMIMaxx actually makes 2 tyres per 60 SEC cycle and update CLAUDE.md §4 accordingly

**Why:** The conflict is CLAUDE.md spec (60 SEC/tyre) vs pilot.yaml config (2 tyres/cycle = 30 SEC/tyre). Industry benchmark strongly supports 60 SEC/tyre. The 34-min Building duration is causing the 2 LATE OTIF violations (Building finishes but upstream compound scheduling is compressed).

**How to apply:** In next QA run, check Building duration. Expected = ceil(ceil(qty/1)/0.95) = ceil(qty/0.95). For qty=64, expect 68 min. If 34, tyres_per_cycle=2 is still set.
