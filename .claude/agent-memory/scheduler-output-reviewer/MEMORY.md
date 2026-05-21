# Scheduler Output Reviewer — Agent Memory Index

- [Run 1107-21-05-2026 Findings](run_1107_21_05_2026_findings.md) — first full QA run; 3 critical defects found (L1 violation, Building duration miscalculation, 41 undetected aging-MAX violations)
- [Recurring Defect Signatures](recurring_defect_signatures.md) — patterns seen across runs: silent aging violations, Building duration errors, L1 grain violations
- [Reusable QA Query Snippets](reusable_qa_queries.md) — pandas one-liners for reservation log, double-booking, gap vs max_aging, duration check
- [Run 2327-21-05-2026 Findings](run_2327_21_05_2026_findings.md) — second QA run; 3 of 6 prior defects fixed; 2 new defects (building_to_curing missing infeasible rows, double-ceil on M/MIN FRC lots)
