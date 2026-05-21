---
name: recurring-defect-signatures
description: Defect patterns seen across V1 scheduler runs — use as first-pass checklist
metadata:
  type: project
---

# Recurring Defect Signatures

## 1. Silent aging-MAX violations on Building→Curing edge
- **Signature:** `building_to_curing.csv` shows all rows as EARLY, `aging_violations.csv` is empty, OTIF=0%.
- **Root cause:** Diagnostics module not evaluating the Building→Curing edge against max_aging_min. `gap_min >> max_aging_min` (e.g., 21770 vs 4320 min).
- **First check:** `(btc['gap_min'] > btc['max_aging_min']).sum()` — if > 0, diagnostics is broken.
- **Module:** `diagnostics.py` aging-violations sweep.

## 2. Building lot duration too small (factor ~300+ error)
- **Signature:** Building lots with 640 tyres have `duration_min=2`.
- **Root cause:** `time_calculation.py` treats SEC per tyre (UOM=SEC) as SEC/BATCH with batch=1 instead of multiplying by tyre count.
- **Expected floor:** Any Building lot for ≥64 tyres should have `duration_min ≥ 68` (= ceil(64*60/60/0.95)).
- **Module:** `time_calculation.py` — UOM handler for VMIMaxx Building machines.

## 3. L1 grain violation — lot aggregation across curing blocks
- **Signature:** 5 Building lots for 41+ curing blocks, each `serves_blocks` lists 10 block IDs.
- **Root cause:** Lot-sizing module aggregates Building demand across blocks (correct for compounds, wrong for Green Tyre Building which is L1 per-block).
- **Module:** `lot_sizing.py` — needs special case: Green Tyre (op_seq=70) must not aggregate across curing blocks.

## 4. Missing block coverage (b42)
- **Signature:** `building_to_curing.csv` has 41 rows, not 42.
- **Likely cause:** Indexing off-by-one in demand explosion or lot-sizing block enumeration.
- **Module:** `demand_explosion.py` or `lot_sizing.py`.

## 5. on_time_flag missing from schedule.csv
- **Signature:** Column not present in `schedule.csv`.
- **Module:** `writer.py` — output schema enforcement (Section 11).

## KPI plausibility ranges (first run)
- OTIF=0% with all-EARLY classification = diagnostics bug, not truly 0% on-time
- FRC util=100% over its own span is EXPECTED (back-to-back CPJ1218+EHT1000 with no gaps)
- Mixer 0206 util=97.7% = plausible for bottleneck compound
- Building machine_6001 util=3.3% over full schedule span = expected given Building takes only 2 min (wrong) out of 1574 min span
