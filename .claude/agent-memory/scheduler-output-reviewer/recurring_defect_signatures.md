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

## Run 2327-21-05-2026 additions

### Partial fix pattern: Building duration halved
- After fixing the "2 min per lot" bug (treating 60 SEC/tyre as SEC/BATCH), the new code produces 34 min instead of 68 min for 64-tyre lots.
- 34 = ceil(32/0.95). So qty=32 is being used instead of qty=64.
- Hypothesis: either lot_sizing.py is halving qty before passing to time_calculation, or time_calculation is receiving half the batch. Check for integer division (qty // 2) or a hardcoded batch_size=2 assumption somewhere in time_calculation.py for 'SEC' UOM without batch_size in routing.
- Reusable check: `bldg['duration_min'].unique()` -- should be 68 for qty=64. If 34, qty is halved.

### building_to_curing.csv missing infeasible blocks
- diagnostics.py only writes rows for successfully scheduled Building lots.
- Per CLAUDE.md §11, infeasible blocks must also appear (classified as INFEASIBLE or similar).
- Symptom: row count < 42 when infeasibilities exist.
- Check: `len(pd.read_csv('building_to_curing.csv')) == 42` -- must always be true for pilot.

### Double-ceil on M/MIN duration (FRC)
- time_calculation.py computes ceil(qty_M / proc_rate) first (integer), then ceil(result / 0.95).
- L20 mandates single ceil: `ceil(qty_M / proc_rate / 0.95)`.
- Effect is small (1 min over for most FRC lots) but is a spec violation.
- CPJ1218 FRC example: 243840 MM at 20 M/MIN -- single ceil gives 13 min, double gives 14.

### t0 dynamic computation vs placeholder
- CLAUDE.md L17 says use 2026-05-01 07:00 as placeholder.
- Run 2327 uses t0=2026-05-16 13:58 (dynamically computed earliest mixer start).
- This is more correct but audit_report.md should document it explicitly.
- Verify by: `pd.read_csv('schedule.csv')['start_dt'].min()` -- that's t0.
