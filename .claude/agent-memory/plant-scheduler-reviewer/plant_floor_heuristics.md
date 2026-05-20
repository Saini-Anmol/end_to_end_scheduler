---
name: plant-floor-heuristics
description: Tyre-plant operational rules of thumb that recur in scheduling critiques
metadata:
  type: reference
---

Industry-practice heuristics (state as opinion in critiques, not as data facts).

**Why:** these come from PCR plant operations experience and explain WHY certain brief decisions are correct. They are not in the brief but they justify the brief's choices.

**How to apply:** cite as "Industry practice" or "Plant-floor observation" in critiques, never as hard data.

- **FRC (four-roll calendar) is the throat of the rubber plant.** Calendering rubberised steel belt and ply is hot, slow, and has tight changeover discipline because of compound contamination. For the BTP pilot, FRC sees CPJ1218 ×2 cuts + EHT1000 ×2 cuts = 4 distinct calender runs per Building lot, plus whatever 95 other SKUs in the May plan demand. Single FRC = single bottleneck for the whole plant. With V1 changeover at 0, FRC contention is purely capacity, but it still binds first.
- **Mixing-room compound aging cuts both ways.** MIN aging is for dispersion/cooling — undershoot means scrap in the next step (porosity, blisters). MAX aging is for scorch — overshoot means the compound has started cross-linking and is unusable. The MAX is a HARD constraint, not advisory.
- **Sidewall (SSW) is the most aging-sensitive component on a tyre.** It has high carbon black, oils, and a long compound chain (multiple master mixes feeding final mix). Once it exceeds aging-MAX, scrap rate spikes. SSW MAX of 72 Hours / MIN 2 Hours per the pilot Aging Master is reasonable but tight when stacked with FRC contention upstream.
- **Mixing-room batch aggregation is normal.** A mixer runs 200-400 kg batches; a 64-tyre Building lot rarely needs a fresh mixer batch. Aggregation across multiple curing blocks (Section 8.C) reflects real plant behaviour and reduces FRC pressure too.
- **Building machine pinning (L3) is floor-discipline, not optimisation.** The shift supervisor wants one machine running one SKU all day for traceability, defect-tracing, and operator familiarity. Spilling to a 2nd machine is a flag that something upstream is slipping.
- **VIPO bead bundler is rarely the bottleneck.** Cycle time is short relative to demand. But the Fillering operation downstream (where bead apex is married to the bead bundle) is where the BD-12843443-4 null `proc_time` lives — and without that number nothing in the bead chain can be scheduled.
- **A 24×7 plant has natural micro-gaps for cleaning, banbury sweeps, calender roll cleaning.** The brief intentionally ignores these. Good for V1. In a real shift, planners pad 5-10% on shared machines.
- **Curing presses are sacred.** Once a press is in the LP (long-period) plan, it does not move. The brief's "never shift curing" is plant gospel.

