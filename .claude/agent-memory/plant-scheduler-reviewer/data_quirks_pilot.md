---
name: data-quirks-pilot
description: Specific data-quality landmines in the BTP pilot inputs that planners repeatedly trip on
metadata:
  type: project
---

The pilot SKU `1325220516095HTMX0` has 42 curing blocks (mostly 64 tyres / 8-hr block / 15-min cycle) on press 14811. Total demand 2,620 tyres. Routing sheet has 62 rows; BOM 65 rows.

**Why:** these recur in every review of a proposed approach and the planner usually under-specifies how each is handled. Cite them by Section 9 finding number when reviewing.

**How to apply:** when reviewing an approach, check whether each of these is explicitly addressed:

- Aging Master duplicates with conflicting values: `EHT1000` appears with both (3 Days max / 2 Hours min) and (3 Days max / 4 Hours min). `IL3` repeats 3D/4H many times. Several `MT3704` rows show 15/3 and 15/0 D/H. Section 9 finding 1 demands unit normalisation; planner must also declare which row wins on conflict (or HALT).
- Mixed units within a single row (`B460` Min=4 Hours, Max=4 Days). Normalise to minutes per Section 9 finding 1.
- Duplicate EHT1000 calendering routing row at Excel row 51 (`is_primary` NaN) — L7 says use `is_primary == 1.0`.
- Null `proc_time` on `BD-12843443-4` Fillering row — L8.D demands HALT, not impute.
- `transfer_time_min` is null on most rows → 10-min default (Section 9 finding 3).
- `alt_machine_count` wrong on many rows → derive `eligible_machine_count` (Section 8.F).
- Capstrip chain entirely out (L12) — must not appear in output sheets, only labelled in BOM viz.
- "Work Away" entries (IL3 WA, JT444WA, HS106 WA, T4004WA) are reclaim — not scheduled (L13).
- FRC is single shared machine carrying CPJ1218 ×2 cuts AND EHT1000 ×2 cuts (4 rows for the pilot) — the most-likely bottleneck for V1.
- Pilot building op is `VMIMaxx GROUP` at 60 SEC/tyre. One block = 64 tyres = ~67 min on one Building machine after L10 efficiency.

