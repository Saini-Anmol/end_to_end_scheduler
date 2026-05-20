---
name: v1-boundary
description: What is in V1 scope vs deferred, so reviews don't unfairly penalise V1-correct approaches
metadata:
  type: project
---

V1 = demand fulfilment only. V2 = optimisation on top.

**Why:** the planner has explicitly de-scoped changeover and utilisation-as-objective for V1 (Section 1.5, L8). A review that demands these features in V1 is wrong.

**How to apply:** in Section 5 (Enhancements), tag each suggestion V1 or V2. If a weakness is purely about a V2 concern (e.g., "doesn't cluster same-product runs on FRC"), it goes in V2 enhancements, NOT in Section 3 disadvantages.

In V1 the engine MUST:
- Be deterministic (L4.6) — same inputs, byte-identical outputs.
- Pin Tyre Building to a primary machine (L3), spill only on aging-window violation.
- Treat changeover = 0 min (L8) — log routed_product but no time consumed.
- HALT on missing `proc_time` (Section 8.D) and missing Aging/ItemType rows (Section 9 finding 8).
- Skip Capstrip chain entirely except in BOM viz with "OUT OF SCOPE" label (L12).
- Apply efficiency uniformly (`effective_time = nominal / 0.95`, L10).
- Use Least Slack First dispatch with the three documented tiebreakers (Section 8.I).
- Report aging violations, Building→Curing handoff, infeasibilities — never repair (L11).

In V1 the engine MUST NOT:
- Be penalised for ignoring changeover minutes.
- Be penalised for not optimising machine utilisation (but it must REPORT utilisation in the KPI sheet).
- Be penalised for not clustering same-product lots on shared machines (FRC, mixers).

