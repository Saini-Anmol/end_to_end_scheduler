---
name: approach-pitfalls
description: Recurring mistakes in proposed scheduling approaches for the BTP pilot
metadata:
  type: feedback
---

When reviewing a proposed scheduling approach, watch for these recurring weaknesses.

**Why:** these patterns show up in nearly every reviewer's first draft because they confuse "what the brief says" with "what feels intuitive as a scheduler". Calling them out crisply saves the planner a rebuild.

**How to apply:** if any of these appear in a proposed approach, flag them in Section 3 or Section 6 of the critique, with brief section cite.

- **Backward-window planner as a separate pass.** The brief locks a forward pass anchored to fixed curing (Section 1, L1, L4.5). A backward "latest acceptable start" calculation per lot is fine as a *bookkeeping* step that produces the slack value used by Least Slack First — but it must NOT become an MRP-style backward-explosion plan that competes with the forward pass. Flag any proposal that runs scheduling backward.
- **Flat slack buffer (e.g., "15 or 20 min" extra).** The brief uses actual aging MIN/MAX per BOM edge plus `effective_gap = MAX(transfer_time, MIN_aging)` (L14). A global slack pad either double-counts MIN_aging or is silently overridden by it. Push back.
- **Rescheduling/repair loop after constraint validation.** L11 says flag and continue. A re-plan loop threatens determinism (L4.6) because outputs become path-dependent on iteration order. L3's Building spill-to-secondary is the only sanctioned in-pass repair.
- **FEFO without scoping the pool.** [[v1-boundary]] FEFO per Section 8.I matches a consumer lot to one of multiple committed producer lots. Question the pool: is it (a) physically completed producer lots that have cleared MIN_aging, or (b) committed-but-still-running future lots? V1 should answer (a).
- **Missing tiebreakers in Least Slack First.** Section 8.I specifies (1) earliest curing-block deadline, (2) longest downstream path, (3) ItemCode lex. Planner usually mentions LSF top-level only.
- **Treating master-to-master edges as zero-gap.** L6 says full aging window applies on master→master (e.g., MB230→MB231). Approaches that walk only producer→consumer-of-different-type miss this.
- **Defaulting silently on null `proc_time`.** Section 8.D says HALT. Any "we'll impute" or "we'll use a default" needs to be challenged.
- **Forgetting AND-join arithmetic.** All 8 components must be ready and in-window AT THE SAME consumer_start. Per-component aging-MAX backed up from Building start is the binding upper bound.
- **Capstrip leaking into the schedule.** L12 says skip everywhere except optionally labelled in BOM viz.

