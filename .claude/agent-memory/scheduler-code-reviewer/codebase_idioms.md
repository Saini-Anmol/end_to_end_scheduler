---
name: codebase-idioms
description: Patterns in BTP scheduler code that look suspicious but are correct
metadata:
  type: project
---

## Idioms verified correct as of 2026-05-21

### `to_minute` uses floor division (not ceil)
`V1/utilities/time_math.py:22`: `return int(delta_s // 60)`
This is correct for datetime→minute conversion. The spec mandates `(inst − t0).total_seconds() // 60`
(L20). This is FLOOR not CEIL. The single-ceil rule (L20) applies to PROCESSING time
conversion, not to wall-clock anchoring. Do not flag as rounding-direction error.

### `is_expired` uses `<` not `<=` in fefo.py
`V1/utilities/fefo.py:27`: `return self.end_min + self.max_aging_min < at_min`
This means a lot is expired when `at_min > end + max` — i.e., eligible when
`at_min <= end + max`. This is CORRECT per L22: consumer_start = end + max is
COMPLIANT (inclusive). The `<` for expiry and `>` for violation in diagnostics are
correct together.

### `latest_acceptable_end_min` instead of `latest_acceptable_start_min`
`V1/models/feasibility.py` and `V1/routes/backward_feasibility.py` store END time,
not start time. CLAUDE.md says "scalar `latest_acceptable_start`" but the V1 
simplification stores end time and notes the scheduler derives start = end - duration.
This is documented in `feasibility.py:12-14`. Not a defect.

### Explode_block for diamond BOM items
`V1/routes/demand_explosion.py:87-96`: When the same child item appears via two BOM
paths (CPJ1218 via both CPJ1218-162MM and CPJ1218-154MM), qty is accumulated in
`qty_by_item` dict. Each item_code appears ONCE in the result dict. Diamond BOM does
NOT cause duplicate `serves_blocks` entries. Verified 2026-05-21.

### `effective_min = ceil(nominal_min / 0.95)` order
`V1/utilities/time_math.py:40`: `apply_efficiency(nominal_min, factor)` uses
`int(math.ceil(nominal_min / factor))`. The efficiency divisor is applied then ceil.
This matches L10 exactly. Don't suggest changing the order.

### Run-id uses wall clock for FOLDER naming only
`V1/setups/run_context.py:36`: `stamp = (now or datetime.now()).strftime(...)` 
This is acceptable per CLAUDE.md Section 13: "run_id based on wall clock is OK for
*folder naming* but must not appear in any data row." Verified: run_id does not appear
in any CSV data rows.

### `_dedup_aging` groupby after sort
`V1/routes/audit.py:427`: `aging_sorted.groupby("ItemCode", dropna=False, sort=False)`
This uses `sort=False` but operates on `aging_sorted` which is pre-sorted. The
`sort=False` just preserves the pre-sorted order (avoids redundant re-sort).
Deterministic because the input was sorted. Not a dict-iteration issue.
