# Scheduler Output Reviewer — Agent Memory Index

- [Run 1107-21-05-2026 Findings](run_1107_21_05_2026_findings.md) — first full QA run; 3 critical defects found (L1 violation, Building duration miscalculation, 41 undetected aging-MAX violations)
- [Recurring Defect Signatures](recurring_defect_signatures.md) — patterns seen across runs: silent aging violations, Building duration errors, L1 grain violations, BLOCK_OVERLAP misfires, lot-sizing alignment defects
- [Reusable QA Query Snippets](reusable_qa_queries.md) — pandas one-liners for reservation log, double-booking, gap vs max_aging, duration check
- [Run 2327-21-05-2026 Findings](run_2327_21_05_2026_findings.md) — second QA run; 3 of 6 prior defects fixed; 2 new defects (building_to_curing missing infeasible rows, double-ceil on M/MIN FRC lots)
- [Input Data Quality Findings](input_data_quality_findings.md) — 2026-05-22 audit of all raw input files; 13 defects catalogued; data-vs-code fix split documented
- [Processing Time Convention Finding](processing_time_convention_finding.md) — VMIMaxx cycle_size=2 in pilot.yaml conflicts with CLAUDE.md sec-per-tyre spec; all M/MIN and Mixing ops correct
- [Run 0013-22-05-2026 Findings](run_0013_22_05_2026_findings.md) — focused review; MPQ not enforced (56 lots below min); SSW case-mismatch; building duration bug persists
- [Run 2355-26-05-2026 Findings](run_2355_26_05_2026_findings.md) — coverage regression to 21/42 GT lots; BLOCK_OVERLAP misfire in multi-producer FEFO loop; 4 aging violations = lot-sizing alignment defect (V1); L16 invariant clean; JIT pass limitation documented
