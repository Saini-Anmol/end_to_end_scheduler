---
name: module-hotspots
description: Risk ranking of BTP scheduler modules by defect likelihood
metadata:
  type: project
---

## Risk ranking (as of 2026-05-21)

1. **`V1/setups/guardrails.py`** — STUB. Two critical/medium assertions unimplemented:
   L17 t0 guardrail and Section 16 reservation invariant. Every review should check
   if this stub has been filled.

2. **`V1/routes/forward_scheduler.py`** — The L3/L18 building primary spill logic is
   wrong (picks by earliest-end, not by aging-MAX constraint). Also defers L21/L15/L16
   — any future upgrade to event-heap dispatch will touch this file extensively.

3. **`V1/utilities/event_heap.py`, `lsf_tiebreak.py`, `reservation_table.py`** — All
   stubs. Will become live when L21/L15/L16 are implemented. High risk when coded.

4. **`V1/routes/lot_sizing.py`** — Complex forward-aggregate + HALT logic. Verified
   correct in session 2026-05-21. Low ongoing risk but worth re-checking if BOM or
   MPQ data changes.

5. **`V1/reports/writer_bom_graph.py`** — Non-deterministic: `nx.topological_sort`
   is documented as non-unique. Different runs produce different edge layouts in the SVG.
   Fix: replace with `nx.lexicographical_topological_sort` and sort within-level nodes.

6. **`V1/reports/writer_gantt.py`** — Non-deterministic: plotly generates `uuid4` div IDs.
   Only cosmetic (doesn't affect scheduling data), but violates L4.6 byte-identical outputs.

7. **`V1/utilities/fefo.py`** — Short and clean. L22 boundary comparisons verified
   correct. Low ongoing risk.

6. **`V1/routes/audit.py`** — Solid. All Section 9 findings correctly classified.
   Only cosmetic issue: AgingUnit enum misses 'Min'/'Hr' aliases.
